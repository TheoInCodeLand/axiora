import os
from dotenv import load_dotenv
from fastembed import TextEmbedding
from database.vector_db import get_pinecone_index
from groq import AsyncGroq

print("--> [SYSTEM] Initializing FastEmbed for search queries...")
embedding_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

print("--> [SYSTEM] Initializing Groq Client...")

groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

async def generate_answer(customer_id: str, user_question: str):
    print(f"--> [DEBUG] Searching knowledge base for: '{user_question}'")
    
    # 1. Convert the question into 384-dimensional math
    query_generator = embedding_model.embed([user_question])
    query_embedding = list(query_generator)[0].tolist()

    # 2. Search Pinecone for the top 5 most relevant chunks
    index = get_pinecone_index()
    search_results = index.query(
        namespace=customer_id,
        vector=query_embedding,
        top_k=5, 
        include_metadata=True
    )

    # Extract the text blocks from the search results
    retrieved_chunks = []
    for match in search_results['matches']:
        if 'metadata' in match and 'text' in match['metadata']:
            retrieved_chunks.append(match['metadata']['text'])

    if not retrieved_chunks:
        return {"answer": "No relevant information was found in the database.", "sources": 0}

    # Combine the chunks into one context string
    context_text = "\n\n---\n\n".join(retrieved_chunks)
    print(f"--> [DEBUG] Retrieved {len(retrieved_chunks)} chunks from Pinecone.")

    # 3. Build the precise prompt for the Llama-3 model
    system_prompt = (
        "You are an intelligent, helpful AI assistant. Answer the user's question using ONLY the provided context. "
        "If the answer is not explicitly contained in the context, say 'That information is not in the knowledge base.' "
        "If the context contains relevant markdown links like [Link Text](url), provide them to the user."
    )
    
    user_prompt = f"Context:\n{context_text}\n\nQuestion: {user_question}"

    print("--> [DEBUG] Sending context and question to Groq (Llama-3)...")
    
    # 4. Generate the response using Groq's blazing-fast infrastructure
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.1-8b-instant", # Lightweight, highly capable open-source model
            temperature=0.2, # Low temperature keeps the AI factual and prevents hallucinations
        )

        answer = chat_completion.choices[0].message.content
        print("--> [DEBUG] Answer generated successfully.")
        
        return {
            "answer": answer,
            "sources_used": len(retrieved_chunks)
        }
    except Exception as e:
        print(f"--> [DEBUG] GROQ API ERROR: {e}")
        raise e