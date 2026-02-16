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