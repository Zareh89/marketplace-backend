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