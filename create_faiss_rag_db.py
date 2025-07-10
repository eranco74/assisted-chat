#!/usr/bin/env python3

"""
Faiss RAG Database Builder for Llama Stack

This script processes Markdown files from a directory and creates a Faiss vector database
for use with llama-stack. The script handles text chunking, embedding generation, and
database creation using the llama-stack client.

The script downloads and uses the actual embedding model from the OpenShift Lightspeed RAG Content
repository (https://github.com/openshift/lightspeed-rag-content/tree/main/embeddings_model)
including the model.safetensors file as specified in artifacts.lock.yaml.

Usage:
    python create_faiss_rag_db.py /path/to/markdown/files [OPTIONS]

Requirements:
    - llama-stack-client
    - markdownify (for HTML to markdown conversion if needed)
    - python-frontmatter (for markdown frontmatter parsing)
    - sentence-transformers (for local model loading)
    - git (for cloning the repository)
"""

import argparse
import os
import hashlib
import logging
import re
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import time
import uuid
import sys

try:
    from llama_stack_client import LlamaStackClient
    import frontmatter
    from sentence_transformers import SentenceTransformer
    import urllib.request
    import yaml
except ImportError:
    print(
        "Error: One or more required packages are not installed. "
        "Please run: pip install -r requirements.txt"
    )
    sys.exit(1)

# Configuration constants
OPENSHIFT_LIGHTSPEED_REPO = "https://github.com/openshift/lightspeed-rag-content.git"
EMBEDDING_MODEL_PATH = "embeddings_model"
MODELS_CACHE_DIR = os.path.expanduser("~/.cache/openshift_lightspeed_models")


class OpenShiftLightspeedEmbeddings:
    """Handles downloading and loading OpenShift Lightspeed embedding model"""

    def __init__(self, cache_dir: str = MODELS_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.repo_dir = self.cache_dir / "lightspeed-rag-content"
        self.model_dir = self.repo_dir / EMBEDDING_MODEL_PATH
        self.model = None

    def ensure_model_downloaded(self) -> Path:
        """Download/update the OpenShift Lightspeed RAG content repository"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if self.repo_dir.exists():
            logging.info(f"Updating existing repository at {self.repo_dir}")
            try:
                subprocess.run(
                    ["git", "pull"],
                    cwd=self.repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                logging.warning(f"Git pull failed: {e.stderr}. Re-cloning...")
                shutil.rmtree(self.repo_dir)
                self._clone_repo()
        else:
            logging.info(f"Cloning OpenShift Lightspeed RAG content to {self.repo_dir}")
            self._clone_repo()

        # Verify model files exist
        if not self.model_dir.exists():
            raise FileNotFoundError(
                f"Embedding model directory not found: {self.model_dir}"
            )

        # Download missing artifacts according to artifacts.lock.yaml
        self._download_artifacts()

        model_safetensors = self.model_dir / "model.safetensors"
        if not model_safetensors.exists():
            raise FileNotFoundError(f"model.safetensors not found: {model_safetensors}")

        logging.info(f"OpenShift Lightspeed model ready at: {self.model_dir}")
        return self.model_dir

    def _clone_repo(self):
        """Clone the OpenShift Lightspeed RAG content repository"""
        try:
            subprocess.run(
                ["git", "clone", OPENSHIFT_LIGHTSPEED_REPO, str(self.repo_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to clone repository: {e.stderr}")

    def _download_artifacts(self):
        """Download missing artifacts according to artifacts.lock.yaml"""
        artifacts_lock_path = self.repo_dir / "artifacts.lock.yaml"

        if not artifacts_lock_path.exists():
            logging.warning(f"artifacts.lock.yaml not found at {artifacts_lock_path}")
            return

        try:
            with open(artifacts_lock_path, "r") as f:
                artifacts_config = yaml.safe_load(f)

            if "artifacts" not in artifacts_config:
                logging.warning("No artifacts section found in artifacts.lock.yaml")
                return

            for artifact in artifacts_config["artifacts"]:
                filename = artifact["filename"]
                download_url = artifact["download_url"]
                expected_checksum = artifact.get("checksum", "")

                # Check if file exists in model directory
                file_path = self.model_dir / filename

                if file_path.exists():
                    # Verify checksum if provided
                    if expected_checksum and self._verify_checksum(
                        file_path, expected_checksum
                    ):
                        logging.info(
                            f"✅ {filename} already exists with correct checksum"
                        )
                        continue
                    elif not expected_checksum:
                        logging.info(
                            f"✅ {filename} already exists (no checksum verification)"
                        )
                        continue
                    else:
                        logging.warning(
                            f"⚠️ {filename} exists but checksum mismatch. Re-downloading..."
                        )

                # Download the file
                logging.info(f"📥 Downloading {filename} from {download_url}")
                try:
                    urllib.request.urlretrieve(download_url, file_path)

                    # Verify checksum after download
                    if expected_checksum:
                        if self._verify_checksum(file_path, expected_checksum):
                            logging.info(
                                f"✅ {filename} downloaded and verified successfully"
                            )
                        else:
                            logging.error(
                                f"❌ {filename} downloaded but checksum verification failed"
                            )
                            file_path.unlink()  # Remove corrupted file
                            raise RuntimeError(
                                f"Checksum verification failed for {filename}"
                            )
                    else:
                        logging.info(f"✅ {filename} downloaded successfully")

                except Exception as e:
                    logging.error(f"❌ Failed to download {filename}: {e}")
                    if file_path.exists():
                        file_path.unlink()  # Clean up partial download
                    raise RuntimeError(f"Failed to download {filename}: {e}")

        except Exception as e:
            logging.error(f"Failed to process artifacts.lock.yaml: {e}")
            raise RuntimeError(f"Failed to process artifacts.lock.yaml: {e}")

    def _verify_checksum(self, file_path: Path, expected_checksum: str) -> bool:
        """Verify file checksum"""
        try:
            # Extract algorithm and hash from checksum string (e.g., "sha256:abc123...")
            if ":" in expected_checksum:
                algorithm, expected_hash = expected_checksum.split(":", 1)
            else:
                algorithm = "sha256"
                expected_hash = expected_checksum

            # Calculate actual hash
            hash_obj = hashlib.new(algorithm)
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_obj.update(chunk)
            actual_hash = hash_obj.hexdigest()

            return actual_hash == expected_hash

        except Exception as e:
            logging.error(f"Failed to verify checksum for {file_path}: {e}")
            return False

    def load_model(self) -> SentenceTransformer:
        """Load the OpenShift Lightspeed embedding model"""
        if self.model is None:
            model_path = self.ensure_model_downloaded()
            logging.info(f"Loading OpenShift Lightspeed model from {model_path}")

            try:
                self.model = SentenceTransformer(str(model_path))
                logging.info(
                    f"Model loaded successfully. Embedding dimension: {self.model.get_sentence_embedding_dimension()}"
                )
            except Exception as e:
                logging.error(f"Failed to load model from {model_path}: {e}")
                # Fallback to downloading from HuggingFace
                logging.info("Falling back to downloading model from HuggingFace")
                self.model = SentenceTransformer(
                    "sentence-transformers/all-mpnet-base-v2"
                )

        return self.model

    def get_embedding_dimension(self) -> int:
        """Get the embedding dimension of the model"""
        if self.model is None:
            self.load_model()
        return self.model.get_sentence_embedding_dimension()


class MarkdownProcessor:
    """Handles processing of markdown files"""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def find_markdown_files(
        self, directory: Path, pattern: str = "*.md", recursive: bool = True
    ) -> List[Path]:
        """Find all markdown files in directory"""
        if recursive:
            return list(directory.rglob(pattern))
        else:
            return list(directory.glob(pattern))

    def process_markdown_file(self, file_path: Path) -> Dict[str, Any]:
        """Process a single markdown file and extract content and metadata"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                post = frontmatter.load(f)

            # Extract metadata
            metadata = {
                "filename": file_path.name,
                "filepath": str(file_path),
                "size": file_path.stat().st_size,
                "modified": file_path.stat().st_mtime,
                **post.metadata,
            }

            # Get content
            content = post.content.strip()

            return {
                "content": content,
                "metadata": metadata,
                "chunks": self._create_chunks(content, metadata),
            }

        except Exception as e:
            logging.error(f"Error processing {file_path}: {e}")
            return None

    def _create_chunks(
        self, content: str, metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Split content into overlapping chunks"""
        if not content:
            return []

        words = content.split()
        chunks = []

        for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
            chunk_words = words[i : i + self.chunk_size]
            chunk_text = " ".join(chunk_words)

            # Create unique chunk ID
            chunk_id = hashlib.md5(f"{metadata['filepath']}-{i}".encode()).hexdigest()

            chunk_metadata = {
                **metadata,
                "chunk_id": chunk_id,
                "chunk_index": i // (self.chunk_size - self.chunk_overlap),
                "chunk_start_word": i,
                "chunk_end_word": i + len(chunk_words),
                "chunk_size": len(chunk_words),
            }

            chunks.append(
                {"id": chunk_id, "content": chunk_text, "metadata": chunk_metadata}
            )

        return chunks


class FaissRAGBuilder:
    """Main class for building Faiss RAG database"""

    def __init__(
        self,
        llama_stack_url: str = "http://localhost:8321",
        api_key: Optional[str] = None,
        provider_id: str = "faiss",
        cache_dir: str = MODELS_CACHE_DIR,
    ):
        self.llama_stack_url = llama_stack_url
        self.api_key = api_key
        self.provider_id = provider_id
        self.cache_dir = cache_dir

        # Initialize components
        self.embeddings = OpenShiftLightspeedEmbeddings(cache_dir)
        self.client = None

    def connect_to_llama_stack(self) -> LlamaStackClient:
        """Connect to llama-stack server"""
        try:
            client_config = {"base_url": self.llama_stack_url}
            if self.api_key:
                client_config["api_key"] = self.api_key

            self.client = LlamaStackClient(**client_config)

            # Test connection
            models = self.client.models.list()
            # Handle both old (models.data) and new (direct list) response formats
            if hasattr(models, "data"):
                model_count = len(models.data)
            else:
                model_count = len(models) if isinstance(models, list) else 0
            logging.info(f"Connected to llama-stack. Available models: {model_count}")

            return self.client

        except Exception as e:
            logging.error(
                f"Failed to connect to llama-stack at {self.llama_stack_url}: {e}"
            )
            raise

    def create_vector_database(self, vector_db_id: str) -> bool:
        """Create vector database if it doesn't exist"""
        try:
            # Check if database exists
            try:
                db_info = self.client.vector_dbs.get(vector_db_id=vector_db_id)
                logging.info(f"Vector database '{vector_db_id}' already exists")
                return True
            except:
                pass

            # Get embedding dimension
            embedding_dim = self.embeddings.get_embedding_dimension()

            # Find available embedding model
            models = self.client.models.list()
            embedding_model_id = None

            # Handle both old (models.data) and new (direct list) response formats
            model_list = models.data if hasattr(models, "data") else models

            for model in model_list:
                if hasattr(model, "model_type") and model.model_type == "embedding":
                    embedding_model_id = (
                        model.identifier
                        if hasattr(model, "identifier")
                        else model.model_id
                    )
                    break

            if not embedding_model_id:
                # Fallback to a common embedding model identifier
                embedding_model_id = "sentence-transformers/all-mpnet-base-v2"

            logging.info(f"Using embedding model: {embedding_model_id}")

            # Register new database
            self.client.vector_dbs.register(
                vector_db_id=vector_db_id,
                embedding_model=embedding_model_id,
                embedding_dimension=embedding_dim,
                provider_id=self.provider_id,
            )

            logging.info(f"Registered vector database: {vector_db_id}")
            return True

        except Exception as e:
            logging.error(f"Failed to create vector database: {e}")
            return False

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenShift Lightspeed model"""
        model = self.embeddings.load_model()
        embeddings = model.encode(texts, convert_to_tensor=False)
        return embeddings.tolist()

    def insert_chunks(
        self, vector_db_id: str, chunks: List[Dict[str, Any]], batch_size: int = 100
    ):
        """Insert chunks into vector database"""
        total_chunks = len(chunks)

        for i in range(0, total_chunks, batch_size):
            batch = chunks[i : i + batch_size]

            # Prepare batch data as documents for the new API
            documents = []
            for chunk in batch:
                documents.append(
                    {
                        "document_id": chunk["id"],
                        "content": chunk["content"],
                        "metadata": chunk["metadata"],
                    }
                )

            # Insert batch using the documents API
            try:
                self.client.vector_io.insert(
                    vector_db_id=vector_db_id, documents=documents
                )
                logging.info(
                    f"Inserted batch {i//batch_size + 1}/{(total_chunks + batch_size - 1)//batch_size} ({len(batch)} chunks)"
                )
            except Exception as e:
                logging.error(f"Failed to insert batch {i//batch_size + 1}: {e}")

    def test_query(
        self, vector_db_id: str, query: str, max_chunks: int = 5
    ) -> List[Dict[str, Any]]:
        """Test the RAG database with a query"""
        try:
            response = self.client.vector_io.query(
                vector_db_id=vector_db_id,
                query=query,
                params={"max_chunks": max_chunks, "score_threshold": 0.0},
            )

            results = []
            # Handle different response formats
            if hasattr(response, "chunks") and hasattr(response, "scores"):
                for chunk, score in zip(response.chunks, response.scores):
                    results.append(
                        {
                            "score": score,
                            "content": chunk.content,
                            "metadata": chunk.metadata,
                        }
                    )
            elif hasattr(response, "documents"):
                for doc in response.documents:
                    results.append(
                        {
                            "score": getattr(doc, "score", 0.0),
                            "content": doc.content,
                            "metadata": getattr(doc, "metadata", {}),
                        }
                    )
            else:
                logging.warning("Unknown response format from vector_io.query")

            return results

        except Exception as e:
            logging.error(f"Query failed: {e}")
            return []

    def build_rag_database(
        self,
        directory: str,
        vector_db_id: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        file_pattern: str = "*.md",
        recursive: bool = True,
        batch_size: int = 100,
        test_query: Optional[str] = None,
    ):
        """Main function to build RAG database"""

        # Connect to llama-stack
        logging.info("Connecting to llama-stack...")
        self.connect_to_llama_stack()

        # Initialize processor
        processor = MarkdownProcessor(chunk_size, chunk_overlap)

        # Find markdown files
        directory_path = Path(directory)
        if not directory_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        markdown_files = processor.find_markdown_files(
            directory_path, file_pattern, recursive
        )
        logging.info(f"Found {len(markdown_files)} markdown files to process")

        if not markdown_files:
            logging.warning("No markdown files found!")
            return

        # Create vector database
        logging.info(f"Creating vector database: {vector_db_id}")
        if not self.create_vector_database(vector_db_id):
            raise RuntimeError("Failed to create vector database")

        # Process files and collect chunks
        all_chunks = []

        for file_path in markdown_files:
            logging.info(f"Processing: {file_path}")

            processed = processor.process_markdown_file(file_path)
            if processed and processed["chunks"]:
                all_chunks.extend(processed["chunks"])
                logging.info(
                    f"  Created {len(processed['chunks'])} chunks from {file_path}"
                )

        if not all_chunks:
            logging.warning("No chunks created from any files!")
            return

        logging.info(
            f"Processed {len(markdown_files)} files, created {len(all_chunks)} total chunks"
        )

        # Insert chunks
        logging.info("Inserting chunks into vector database...")
        self.insert_chunks(vector_db_id, all_chunks, batch_size)

        logging.info(
            f"Successfully built RAG database '{vector_db_id}' with {len(all_chunks)} chunks"
        )

        # Test query if provided
        if test_query:
            logging.info(f"Testing with query: '{test_query}'")
            results = self.test_query(vector_db_id, test_query)

            if results:
                logging.info("Query Results:")
                for i, result in enumerate(results):
                    logging.info(f"  {i+1}. Score: {result['score']:.3f}")
                    logging.info(f"     Content: {result['content'][:100]}...")
                    logging.info(
                        f"     File: {result['metadata'].get('filename', 'Unknown')}"
                    )
                    logging.info("     " + "-" * 50)
            else:
                logging.info("No results found for test query")

        logging.info("RAG database creation completed successfully!")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Create Faiss RAG database from markdown files using OpenShift Lightspeed embedding model"
    )

    parser.add_argument("directory", help="Directory containing markdown files")

    parser.add_argument(
        "--vector-db-id",
        default="markdown_docs",
        help="Vector database identifier (default: markdown_docs)",
    )

    parser.add_argument(
        "--llama-stack-url",
        default="http://localhost:8321",
        help="Llama Stack server URL (default: http://localhost:8321)",
    )

    parser.add_argument("--api-key", help="API key for llama-stack authentication")

    parser.add_argument(
        "--provider-id",
        default="faiss",
        help="Vector database provider ID (default: faiss)",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Chunk size in words (default: 1000)",
    )

    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=100,
        help="Chunk overlap in words (default: 100)",
    )

    parser.add_argument(
        "--file-pattern", default="*.md", help="File pattern to match (default: *.md)"
    )

    parser.add_argument(
        "--recursive", action="store_true", help="Process directories recursively"
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for inserting chunks (default: 100)",
    )

    parser.add_argument(
        "--test-query", help="Test query to run after building database"
    )

    parser.add_argument(
        "--cache-dir",
        default=MODELS_CACHE_DIR,
        help=f"Cache directory for OpenShift Lightspeed models (default: {MODELS_CACHE_DIR})",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        # Create RAG builder
        builder = FaissRAGBuilder(
            llama_stack_url=args.llama_stack_url,
            api_key=args.api_key,
            provider_id=args.provider_id,
            cache_dir=args.cache_dir,
        )

        # Build database
        builder.build_rag_database(
            directory=args.directory,
            vector_db_id=args.vector_db_id,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            file_pattern=args.file_pattern,
            recursive=args.recursive,
            batch_size=args.batch_size,
            test_query=args.test_query,
        )

    except KeyboardInterrupt:
        logging.info("Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
