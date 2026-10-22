dev:
	uvicorn app.main:app --reload

install:
	pip install -r requirements.txt

freeze:
	pip freeze > requirements.txt

migrate:
	alembic upgrade head

makemigrations:
	alembic revision --autogenerate -m "$(m)"
backfill-embeddings:
	python -m app.scripts.backfill_embeddings

eval-assistant:
	python -m evals.assistant.run_eval $(ids)
