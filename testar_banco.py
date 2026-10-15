from sqlalchemy import text

from app.database import engine


def main():
    try:
        with engine.connect() as connection:
            resultado = connection.execute(
                text(
                    """
                    SELECT
                        current_database(),
                        current_user,
                        version()
                    """
                )
            ).one()

        print("Conexao realizada com sucesso.")
        print("Banco:", resultado[0])
        print("Usuario:", resultado[1])
        print("Versao:", resultado[2])

    except Exception as error:
        print("Falha na conexao com o PostgreSQL:")
        print(error)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
