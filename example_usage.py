#!/usr/bin/env python3
"""
Example usage of the Faiss RAG database created with create_faiss_rag_db.py

This script demonstrates how to query the RAG database and use it for
question answering with llama-stack, using the actual OpenShift Lightspeed RAG Content
embedding model files (including model.safetensors) cloned from the repository.
"""

import sys
import argparse
from typing import List, Dict, Any

try:
    from llama_stack_client import LlamaStackClient
except ImportError:
    print(
        "Error: llama-stack-client not installed. Run: pip install llama-stack-client"
    )
    sys.exit(1)


def query_rag_database(
    client: LlamaStackClient,
    vector_db_id: str,
    query: str,
    max_chunks: int = 5,
    score_threshold: float = 0.0,
) -> List[Dict[str, Any]]:
    """Query the RAG database and return formatted results."""
    try:
        response = client.vector_io.query(
            vector_db_id=vector_db_id,
            query=query,
            params={"max_chunks": max_chunks, "score_threshold": score_threshold},
        )

        results = []
        for chunk, score in zip(response.chunks, response.scores):
            results.append(
                {"content": chunk.content, "metadata": chunk.metadata, "score": score}
            )

        return results

    except Exception as e:
        print(f"Error querying database: {e}")
        return []


def format_context_for_llm(
    results: List[Dict[str, Any]], max_context_length: int = 2000
) -> str:
    """Format search results into context for LLM."""
    context_parts = []
    total_length = 0

    for i, result in enumerate(results):
        content = result["content"]
        file_name = result["metadata"].get("file_name", "unknown")

        # Add source information
        part = f"[Source {i+1}: {file_name}]\n{content}\n"

        if total_length + len(part) > max_context_length:
            break

        context_parts.append(part)
        total_length += len(part)

    return "\n---\n".join(context_parts)


def answer_question_with_rag(
    client: LlamaStackClient,
    vector_db_id: str,
    question: str,
    model_id: str,
    max_chunks: int = 5,
) -> str:
    """Use RAG to answer a question."""
    # Step 1: Query the vector database
    print(f"🔍 Searching for relevant information about: {question}")
    search_results = query_rag_database(client, vector_db_id, question, max_chunks)

    if not search_results:
        return "I couldn't find relevant information to answer your question."

    print(f"📚 Found {len(search_results)} relevant chunks")

    # Step 2: Format context for the LLM
    context = format_context_for_llm(search_results)

    # Step 3: Create prompt with context
    prompt = f"""Based on the following context, please answer the question accurately and concisely.

Context:
{context}

Question: {question}

Answer:"""

    # Step 4: Generate answer using LLM
    try:
        response = client.inference.chat_completion(
            model_id=model_id,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )

        return response.completion_message.content

    except Exception as e:
        print(f"Error generating answer: {e}")
        return "I encountered an error while generating the answer."


def interactive_qa_session(client: LlamaStackClient, vector_db_id: str, model_id: str):
    """Run an interactive Q&A session."""
    print("\n🤖 Interactive Q&A Session")
    print("Type 'quit' to exit, 'help' for help")
    print("-" * 50)

    while True:
        try:
            question = input("\n❓ Your question: ").strip()

            if question.lower() in ["quit", "exit", "q"]:
                print("👋 Goodbye!")
                break

            if question.lower() == "help":
                print(
                    """
Available commands:
- Type any question to get an answer
- 'quit' or 'exit' to end the session
- 'help' to see this message
                """
                )
                continue

            if not question:
                continue

            # Get answer using RAG
            answer = answer_question_with_rag(client, vector_db_id, question, model_id)

            print(f"\n💡 Answer: {answer}")

        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    """Main function for the example usage script."""
    parser = argparse.ArgumentParser(description="Example usage of Faiss RAG database")
    parser.add_argument(
        "--vector-db-id", default="markdown_docs", help="Vector database identifier"
    )
    parser.add_argument(
        "--llama-stack-url",
        default="http://localhost:8321",
        help="Llama Stack server URL",
    )
    parser.add_argument("--model-id", help="LLM model ID for generating answers")
    parser.add_argument("--question", help="Single question to ask")
    parser.add_argument(
        "--max-chunks", type=int, default=5, help="Maximum number of chunks to retrieve"
    )
    parser.add_argument(
        "--interactive", action="store_true", help="Run in interactive mode"
    )

    args = parser.parse_args()

    # Initialize client
    client = LlamaStackClient(base_url=args.llama_stack_url)

    # Get available models
    try:
        models = client.models.list()
        llm_models = [m for m in models if m.model_type == "llm"]

        if not llm_models:
            print("Error: No LLM models available")
            sys.exit(1)

        # Use specified model or default to first available
        model_id = args.model_id or llm_models[0].identifier
        print(f"Using model: {model_id}")

    except Exception as e:
        print(f"Error getting models: {e}")
        sys.exit(1)

    # Check if vector database exists
    try:
        vector_dbs = client.vector_dbs.list()
        db_exists = any(db.identifier == args.vector_db_id for db in vector_dbs)

        if not db_exists:
            print(f"Error: Vector database '{args.vector_db_id}' not found")
            print("Available databases:")
            for db in vector_dbs:
                print(f"  - {db.identifier}")
            sys.exit(1)

        print(f"✅ Connected to vector database: {args.vector_db_id}")

    except Exception as e:
        print(f"Error checking vector database: {e}")
        sys.exit(1)

    # Run based on mode
    if args.interactive:
        interactive_qa_session(client, args.vector_db_id, model_id)
    elif args.question:
        answer = answer_question_with_rag(
            client, args.vector_db_id, args.question, model_id, args.max_chunks
        )
        print(f"\n❓ Question: {args.question}")
        print(f"💡 Answer: {answer}")
    else:
        # Demo mode - show some example queries
        print("\n📖 RAG Database Demo")
        print("=" * 50)

        # Test basic search
        print("\n🔍 Testing search functionality:")
        test_query = "getting started"
        results = query_rag_database(client, args.vector_db_id, test_query, 3)

        if results:
            print(f"Found {len(results)} results for '{test_query}':")
            for i, result in enumerate(results[:3]):
                print(f"  {i+1}. Score: {result['score']:.3f}")
                print(f"     File: {result['metadata'].get('file_name', 'unknown')}")
                print(f"     Content: {result['content'][:100]}...")
        else:
            print("No results found")

        # Example Q&A
        print(f"\n🤖 Example Q&A using model {model_id}:")
        example_question = "What is this documentation about?"
        answer = answer_question_with_rag(
            client, args.vector_db_id, example_question, model_id
        )
        print(f"❓ Question: {example_question}")
        print(f"💡 Answer: {answer}")

        print(
            "\n💡 Tip: Use --interactive for a Q&A session or --question to ask a specific question"
        )


if __name__ == "__main__":
    main()
