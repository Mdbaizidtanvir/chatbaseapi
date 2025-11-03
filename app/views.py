from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .models import EmbeddingRecord
from .utils import (
    generate_embedding,
    store_embedding,
    fetch_all_user_records,
    delete_file,
    get_all_files,
    query_embedding
)
from .file_reader import extract_text_from_file
import uuid
from django.http import JsonResponse
import openai
import trafilatura
import os

from dotenv import load_dotenv


# Load environment variables from .env
load_dotenv()

# 🔐 API Keys from .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


openai.api_key = OPENAI_API_KEY

def scrape_with_trafilatura(url: str):
    """
    Scrape clean main text content from a URL using trafilatura.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return "[Error: Could not fetch URL content]"
        
        extracted = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        if not extracted:
            return "[Error: No readable text found on page]"
        
        return extracted[:10000]  # limit text size for embedding
    except Exception as e:
        return f"[Error scraping with trafilatura: {e}]"


from rest_framework.permissions import IsAuthenticated

# ----------------------
# Upload & Embed multiple files (per user + bot)
# ----------------------
@method_decorator(csrf_exempt, name='dispatch')
class MultiFileUploadView(APIView):
    #permission_classes = [IsAuthenticated]  # ✅ require JWT

    def post(self, request):
        user_id = request.data.get('user_id')
        bot_id = request.data.get('bot_id')
        files = request.FILES.getlist('files')

        urls = request.data.getlist('urls')  # <--- support multiple URLs from form or JSON

        if (not files and not urls) or not user_id or not bot_id:
            return Response(
                {'error': 'user_id, bot_id, and at least one file or URL required'},
                status=status.HTTP_400_BAD_REQUEST
            )


        results = []

        for file in files:
            try:
                # Extract text safely
                text = extract_text_from_file(file, file.name)
                if not text.strip():
                    results.append({'file_name': file.name, 'error': 'No readable text found'})
                    continue

                # Generate embedding
                embedding = generate_embedding(text)
                index_id = str(uuid.uuid4())

                # Metadata
                metadata = {
                    'user_id': user_id,
                    'bot_id': bot_id,
                    'index_id': index_id,
                    'file_name': file.name
                }

                # Store in Pinecone (per user + bot namespace)
                store_embedding(embedding, metadata, user_id, bot_id, text)

                # Save in DB
                EmbeddingRecord.objects.create(
                    user_id=user_id,
                    bot_id=bot_id,
                    index_id=index_id,
                    file_name=file.name,
                    pinecone_namespace=f"user-{user_id}-bot-{bot_id}"
                )

                results.append({
                    'file_name': file.name,
                    'index_id': index_id,
                    'status': 'embedded'
                })

            except Exception as e:
                results.append({'file_name': file.name, 'error': str(e)})
        
                # Process URLs
        for url in urls:
            try:
                text = scrape_with_trafilatura(url)
                if text.startswith("[Error"):
                    results.append({'url': url, 'error': text})
                    continue

                embedding = generate_embedding(text)
                index_id = str(uuid.uuid4())

                metadata = {
                    'user_id': user_id,
                    'bot_id': bot_id,
                    'index_id': index_id,
                    'file_name': f"URL: {url[:50]}"
                }

                store_embedding(embedding, metadata, user_id, bot_id, text)

                EmbeddingRecord.objects.create(
                    user_id=user_id,
                    bot_id=bot_id,
                    index_id=index_id,
                    file_name=f"url_{index_id}.txt",
                    pinecone_namespace=f"user-{user_id}-bot-{bot_id}"
                )

                results.append({'url': url, 'index_id': index_id, 'status': 'embedded'})

            except Exception as e:
                results.append({'url': url, 'error': str(e)})


        return Response({'results': results}, status=status.HTTP_201_CREATED)


# ----------------------
# Query bot knowledgebase
# ----------------------
@csrf_exempt
def query_bot(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    user_id = request.POST.get("user_id")
    bot_id = request.POST.get("bot_id")
    query_text = request.POST.get("query")
    full_memory = request.POST.get("full_memory", "false").lower() == "true"

    if not user_id or not bot_id or not query_text:
        return JsonResponse({"error": "user_id, bot_id, and query required"}, status=400)

    try:
        # Step 1: Fetch relevant embeddings
        if full_memory:
            result = fetch_all_user_records(user_id=user_id, bot_id=bot_id, top_k=1000)
        else:
            query_vector = generate_embedding(query_text)
            result = query_embedding(user_id=user_id, bot_id=bot_id, query_vector=query_vector, top_k=5)

        # Step 2: Build GPT context
        contexts = []
        for match in result.matches:
            text_content = match.metadata.get("text", "")
            file_name = match.metadata.get("file_name", "Unknown file")
            contexts.append(f"📄 {file_name}\n{text_content}")

        context_text = "\n\n---\n\n".join(contexts) if contexts else "No relevant content found."

        prompt = f"""
You are a helpful assistant. Use the following uploaded documents to answer clearly.

Context:
{context_text}

Question:
{query_text}

Answer:
"""

        # Step 3: GPT Answer
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        answer = response.choices[0].message.content

        return JsonResponse({
            "answer": answer,
            "matches": [
                {"id": m.id, "score": m.score, "metadata": m.metadata} for m in result.matches
            ]
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ----------------------
# Delete file per user + bot
# ----------------------
@csrf_exempt
def delete_user_file(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    user_id = request.POST.get("user_id")
    bot_id = request.POST.get("bot_id")
    file_name = request.POST.get("file_name")

    if not user_id or not bot_id or not file_name:
        return JsonResponse({"error": "user_id, bot_id, and file_name required"}, status=400)

    try:
        success = delete_file(user_id=user_id, bot_id=bot_id, file_name=file_name)
        if success:
            return JsonResponse({"success": True, "message": f"Deleted '{file_name}' for user {user_id}, bot {bot_id}."})
        else:
            return JsonResponse({"success": False, "message": f"No file '{file_name}' found."})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ----------------------
# List all files per user + bot
# ----------------------
@csrf_exempt
def list_user_files(request):
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)

    user_id = request.GET.get("user_id")
    bot_id = request.GET.get("bot_id")

    if not user_id or not bot_id:
        return JsonResponse({"error": "user_id and bot_id required"}, status=400)

    try:
        files = get_all_files(user_id=user_id, bot_id=bot_id)
        return JsonResponse({"success": True, "files": files})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
