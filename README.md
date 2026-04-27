### The source literature of llm building basics

https://github.com/rasbt/LLMs-from-scratch/blob/main/ch02/01_main-chapter-code/ch02.ipynb

### Docker engine
* Start : `docker-compose up -d`
* Stop : `docker-compose dowm`

### Migration scripts
1. `cd app`
2. `alembic init -t async migration`
3. `alembic revision --autogenerate -m "Migration message"`
4. `alembic upgrade head`

### FastAPI server
* `uvicorn app.main:app --reload`
* `/docs` - Swagger documentation

### Enlarging dataset

1. Start pipeline locally with single PDF

    Put the PDF file into `app/ingestion/data/raw/`
    
    Start CLI:

        python -m app.ingestion.run

    or if run.py is inside `app/ingestion/`:

        cd app/ingestion
        python run.py

    After script done check for:

        data/extracted/
        data/processed/scenarios.jsonl
        data/processed/decision_nodes.jsonl
        data/processed/tactics.jsonl
        data/processed/qa_pairs.jsonl
        data/processed/rag_chunks.jsonl
        data/processed/training_samples.jsonl
