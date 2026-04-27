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

1. #### Start pipeline locally with single PDF

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

2. #### Check _extraction_ manually

    Open `qa_pairs.jsonl`, `scenarios.jsonl`, `decision_nodes.jsonl`.

    Check the quality of jsonl to match criteria:

    * are `scenarios` resolving crisis situations;
    * do `decision nodes` have choice logic;
    * `Q&A pairs` are not made-up;
    * are `ua` materials transformed into `en` output;
    * absence of the extra info like типу DOI, УДК, номерів сторінок;
    * double columns PDF are not fused.

    Example:
        
        з USAID manual система має витягти сценарії про кризу в громаді, ризик втрати довіри, потребу в негайній реакції, відмінність інциденту від кризи
        з CERC manual — community stakeholders, advocates/ambivalents/adversaries, crisis coordination/collaboration, рівні engagement .

3. #### Test _FastAPI upload_

    Start backend: `uvicorn app.main:app --reload`
    
    Open Swagger: http://localhost:8000/docs
    
    Check endpoints:
    
         POST /api/v1/ingest/upload
         GET /api/v1/ingest/jobs/{job_id}
         GET /api/v1/ingest/stats
         POST /api/v1/ingest/build-training
    
    Logic behind: 
          
         користувач/admin завантажує PDF, backend запускає background job, а frontend пізніше просто опитує статус.