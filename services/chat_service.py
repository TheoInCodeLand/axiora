import os
from fastembed import TextEmbedding
from database.vector_db import get_pinecone_index
from groq import AsyncGroq

print("--> [SYSTEM] Loading FastEmbed for search queries...")
embedding_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

async def generate_answer(customer_id: str, user_question: str, history: list):
    
    # --- 1. THE BULLETPROOF REFORMULATOR ---
    search_query = user_question
    
    if len(history) > 0:
        # Flatten the history into a script to prevent the AI from "replying" during extraction
        history_script = ""
        for msg in history[-4:]:
            role = "User" if msg.get("role") == "user" else "Consultant"
            history_script += f"{role}: {msg.get('content')}\n"
            
        reformulate_prompt = f"""You are a strict database query extractor. Do NOT act as a conversational AI. Do NOT answer the question.

            Recent Conversation History:
            {history_script}

            New User Input: "{user_question}"

            Task: Rewrite the New User Input into a standalone search query. 
            - Replace pronouns (he, she, his, them, it) with the specific subjects from the history.
            - If the input is just small talk or a greeting (e.g., "hello", "im good"), output EXACTLY: SKIP_SEARCH
            - Output ONLY the standalone rewritten question. Nothing else. Do NOT answer it."""

        try:
            rewrite_completion = await groq_client.chat.completions.create(
                messages=[{"role": "user", "content": reformulate_prompt}],
                model="llama-3.1-8b-instant",
                temperature=0.0, # Zero creativity, strict extraction
                max_tokens=40
            )
            
            rewritten_text = rewrite_completion.choices[0].message.content.strip().replace('"', '')
            
            if "SKIP_SEARCH" in rewritten_text.upper():
                search_query = "SKIP_SEARCH"
            else:
                search_query = rewritten_text
                
        except Exception as e:
            print(f"--> [DEBUG] Reformulator skipped due to error: {e}")

    print(f"--> [DEBUG] Original: '{user_question}' | Pinecone Search: '{search_query}'")
    
    # --- 2. VECTOR SEARCH WITH NAVIGATION METADATA ---
    retrieved_chunks = []
    if search_query != "SKIP_SEARCH":
        query_generator = embedding_model.embed([search_query])
        query_embedding = list(query_generator)[0].tolist()

        index = get_pinecone_index()
        search_results = index.query(
            namespace=customer_id,
            vector=query_embedding,
            top_k=5, 
            include_metadata=True
        )

        for match in search_results['matches']:
            if 'metadata' in match and 'text' in match['metadata']:
                text_chunk = match['metadata']['text']
                # Retrieve the source URL so the consultant knows where the info lives
                source_link = match['metadata'].get('source_url', 'the current page')
                
                # Bind the text to its location for the AI
                retrieved_chunks.append(f"Content: {text_chunk}\nSource Link: {source_link}")

    if not retrieved_chunks:
        context_text = "No direct information found in the database. Rely on general consulting etiquette to guide the user gently."
    else:
        context_text = "\n\n---\n\n".join(retrieved_chunks)

    # --- 3. FINAL GENERATION (The Consultant Persona) ---
    system_prompt = (
        "You are an elite, highly empathetic Client Success Consultant for this website. Your primary mission is to provide 'white-glove' service, ensuring every user feels deeply valued, heard, and supported. "
        "You speak with a warm, natural, and conversational tone—never robotic or overly corporate.\n\n"
        
        "Follow these strict consulting rules:\n"
        "1. THE WHITE-GLOVE EXPERIENCE: Always validate the user's needs. Use active listening cues (e.g., 'That is a great question,' or 'I completely understand why you need that'). Make them feel like your most important client.\n"
        "2. CONVERSATIONAL PROACTIVITY: Answer their question directly, but never let the conversation hit a dead end. Seamlessly weave in a helpful next step, a tailored recommendation, or a polite clarifying question to maintain a natural dialogue.\n"
        "3. PINPOINT NAVIGATION: Act as their personal guide. When providing solutions, use the 'Source Links' in the Knowledge Base Context to point them exactly where they need to go, briefly explaining *why* that specific link will help them.\n"
        "4. THE GRACEFUL PIVOT: If the context completely lacks the answer, never mention your 'database' or 'training.' Instead, validate their request, politely explain that you don't have that specific detail at hand, and immediately pivot to the closest relevant information you DO have, or warmly offer human support.\n"
        "5. ABSOLUTE FACTUAL INTEGRITY: Your empathy must never compromise accuracy. Base all facts, features, and pricing STRICTLY on the provided Knowledge Base Context. Never invent or hallucinate details to appease the user.\n"
        "6. ELEGANT FORMATTING: Keep responses highly readable. Use short, breathable paragraphs. Use bullet points only when listing multiple distinct items. Always end with a warm, open-ended closing."
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-10:]:
        messages.append(msg)
        
    user_prompt = f"Knowledge Base Context:\n{context_text}\n\nNew User Question: {user_question}"
    messages.append({"role": "user", "content": user_prompt})
    
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.1-8b-instant", 
            temperature=0.2, 
        )

        return {
            "answer": chat_completion.choices[0].message.content,
            "sources_used": len(retrieved_chunks)
        }
    except Exception as e:
        raise e