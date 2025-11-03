import os
import openai
from uuid import uuid4
from pinecone import Pinecone, ServerlessSpec

from dotenv import load_dotenv


# Load environment variables from .env
load_dotenv()

# 🔐 API Keys from .env
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


openai.api_key = OPENAI_API_KEY


# ----------------------
# Initialize Pinecone client
# ----------------------
pc = Pinecone(api_key=PINECONE_API_KEY)

# ----------------------
# Helper: sanitize user_id for index name
# ----------------------
def sanitize_index_name(name: str):
    return ''.join(c if c.isalnum() else '-' for c in name.lower())

# ----------------------
# Get or create per-user index
# ----------------------
def get_user_index(user_id):
    sanitized_user = sanitize_index_name(str(user_id))
    index_name = f"user-{sanitized_user}-index"

    existing_indexes = [idx["name"] for idx in pc.list_indexes()]
    if index_name not in existing_indexes:
        pc.create_index(
            name=index_name,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )

    return pc.Index(index_name)

# ----------------------
# Generate embedding
# ----------------------
def generate_embedding(text: str):
    response = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

# ----------------------
# Store embedding per user + bot
# ----------------------
def store_embedding(vector, metadata, user_id, bot_id, text):
    index = get_user_index(user_id)
    vector_id = str(uuid4())
    namespace = f"user-{sanitize_index_name(str(user_id))}-bot-{sanitize_index_name(str(bot_id))}"
    metadata_with_text = metadata.copy()
    metadata_with_text["text"] = text

    index.upsert(
        vectors=[{"id": vector_id, "values": vector, "metadata": metadata_with_text}],
        namespace=namespace
    )
    return vector_id

# ----------------------
# Query embeddings per user + bot
# ----------------------
def query_embedding(user_id, bot_id, query_vector, top_k=5):
    index = get_user_index(user_id)
    namespace = f"user-{sanitize_index_name(str(user_id))}-bot-{sanitize_index_name(str(bot_id))}"
    result = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
        namespace=namespace
    )
    return result

# ----------------------
# Fetch all embeddings for a user + bot
# ----------------------
def fetch_all_user_records(user_id, bot_id, top_k=1000):
    index = get_user_index(user_id)
    namespace = f"user-{sanitize_index_name(str(user_id))}-bot-{sanitize_index_name(str(bot_id))}"
    dummy_vector = [0] * 1536
    result = index.query(
        vector=dummy_vector,
        top_k=top_k,
        include_metadata=True,
        include_values=True,
        namespace=namespace
    )
    return result

# ----------------------
# Get all files for user + bot
# ----------------------
def get_all_files(user_id, bot_id):
    index = get_user_index(user_id)
    namespace = f"user-{sanitize_index_name(str(user_id))}-bot-{sanitize_index_name(str(bot_id))}"
    result = index.query(
        vector=[0]*1536,
        top_k=1000,
        include_metadata=True,
        namespace=namespace
    )
    files = []
    for match in result.matches:
        md = match.metadata
        files.append({
            "id": match.id,
            "file_name": md.get("file_name"),
            "bot_id": md.get("bot_id"),
            "user_id": md.get("user_id"),
            "text_preview": md.get("text","")[:200]
        })
    return files

# ----------------------
# Delete file from user’s index
# ----------------------
def delete_file(user_id, bot_id, file_name):
    index = get_user_index(user_id)
    namespace = f"user-{sanitize_index_name(str(user_id))}-bot-{sanitize_index_name(str(bot_id))}"
    result = index.query(
        vector=[0]*1536,
        top_k=1000,
        include_metadata=True,
        namespace=namespace
    )
    ids_to_delete = [m.id for m in result.matches if m.metadata.get("file_name") == file_name]
    if ids_to_delete:
        index.delete(ids=ids_to_delete, namespace=namespace)
        return True
    return False
