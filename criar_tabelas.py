from sqlalchemy import inspect

from app.database import Base, engine
from app import models  # noqa: F401


def main():
    Base.metadata.create_all(bind=engine)
    tabelas = inspect(engine).get_table_names()
    print("Tabelas criadas/verificadas com sucesso:")
    for tabela in sorted(tabelas):
        print(f"- {tabela}")


if __name__ == "__main__":
    main()
