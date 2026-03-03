import os
import uuid
from fastembed import TextEmbedding
from langchain_text_splitters import RecursiveCharacterTextSplitter
from database.vector_db import get_pinecone_index

# Initialize the local CPU model
# This will download the ~80MB model automatically on the very first run
print("--> [SYSTEM] Initializing Local FastEmbed Engine...")
embedding_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

def chunk_text(text: str):
    print(f"--> [DEBUG] Chunking text of length: {len(text)} characters.")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = splitter.split_text(text)
    print(f"--> [DEBUG] Successfully created {len(chunks)} chunks.")
    return chunks

async def process_and_store(customer_id: str, url: str, markdown_text: str):
    print("--> [DEBUG] Starting process_and_store (Local FastEmbed)...")
    chunks = chunk_text(markdown_text)
    
    if not chunks:
        print("--> [DEBUG] ERROR: No chunks created. The scraped text was empty!")
        return 0

    print(f"--> [DEBUG] Running local CPU embeddings for {len(chunks)} chunks...")
    try:
        # FastEmbed generates the numbers locally without the internet
        embeddings_generator = embedding_model.embed(chunks)
        embeddings = list(embeddings_generator)
        print(f"--> [DEBUG] Local Embedding Success! Generated {len(embeddings)} vectors.")
    except Exception as e:
        print(f"--> [DEBUG] FASTEMBED FATAL ERROR: {e}")
        raise e

    print("--> [DEBUG] Connecting to Pinecone...")
    index = get_pinecone_index()
    vectors = []
    
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        chunk_id = f"{customer_id}-{uuid.uuid4()}"
        vectors.append({
            "id": chunk_id,
            # .tolist() converts the local numpy math into standard numbers for Pinecone
            "values": emb.tolist(), 
            "metadata": {
                "customer_id": customer_id,
                "url": url,
                "text": chunk
            }
        })

    print(f"--> [DEBUG] Upserting {len(vectors)} vectors to Pinecone (Namespace: '{customer_id}')...")
    batch_size = 100
    try:
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            index.upsert(vectors=batch, namespace=customer_id)
            print(f"--> [DEBUG] Uploaded batch of {len(batch)} vectors to Pinecone.")
        print("--> [DEBUG] Pinecone upsert complete!")
    except Exception as e:
        print(f"--> [DEBUG] PINECONE FATAL ERROR: {e}")
        raise e

    return len(chunks)