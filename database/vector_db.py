import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

# Initialize Pinecone Client
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

# This must match the index name you create on the Pinecone website
INDEX_NAME = "axiora-knowledge-base"

def get_pinecone_index():
    """Returns the Pinecone index object."""
    existing_indexes = [index_info["name"] for index_info in pc.list_indexes()]
    
    if INDEX_NAME not in existing_indexes:
        raise Exception(f"Index '{INDEX_NAME}' not found! Please create it in the Pinecone dashboard.")
    
    return pc.Index(INDEX_NAME)