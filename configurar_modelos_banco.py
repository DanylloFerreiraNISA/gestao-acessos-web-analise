from pathlib import Path
import py_compile

ROOT = Path.cwd()
APP = ROOT / 'app'
APP.mkdir(exist_ok=True)
(APP / '__init__.py').touch(exist_ok=True)

MODELS = '''from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Departamento(Base):
    __tablename__ = "departamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    funcionarios: Mapped[list["Funcionario"]] = relationship(back_populates="departamento")
    perfis: Mapped[list["Perfil"]] = relationship(back_populates="departamento")


class Funcionario(Base):
    __tablename__ = "funcionarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(250), index=True)
    departamento_id: Mapped[int | None] = mapped_column(ForeignKey("departamentos.id"), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    incluir_revisao: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    departamento: Mapped["Departamento | None"] = relationship(back_populates="funcionarios")
    perfis: Mapped[list["FuncionarioPerfil"]] = relationship(
        back_populates="funcionario", cascade="all, delete-orphan"
    )


class Perfil(Base):
    __tablename__ = "perfis"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    situacao: Mapped[str] = mapped_column(String(50), default="Pendente", nullable=False)
    departamento_id: Mapped[int | None] = mapped_column(ForeignKey("departamentos.id"), nullable=True)
    ultima_atualizacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    departamento: Mapped["Departamento | None"] = relationship(back_populates="perfis")
    funcionarios: Mapped[list["FuncionarioPerfil"]] = relationship(
        back_populates="perfil", cascade="all, delete-orphan"
    )
    acessos: Mapped[list["PerfilAcesso"]] = relationship(
        back_populates="perfil", cascade="all, delete-orphan"
    )


class Acesso(Base):
    __tablename__ = "acessos"
    __table_args__ = (
        UniqueConstraint("caminho_completo", "tela_final", "botao", name="uq_acesso_caminho_tela_botao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    caminho_completo: Mapped[str] = mapped_column(Text)
    tela_final: Mapped[str] = mapped_column(String(300))
    botao: Mapped[str] = mapped_column(String(300))
    chave_acesso: Mapped[str] = mapped_column(Text, unique=True, index=True)

    perfis: Mapped[list["PerfilAcesso"]] = relationship(
        back_populates="acesso", cascade="all, delete-orphan"
    )


class FuncionarioPerfil(Base):
    __tablename__ = "funcionario_perfis"
    __table_args__ = (
        UniqueConstraint("funcionario_id", "perfil_id", name="uq_funcionario_perfil"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    funcionario_id: Mapped[int] = mapped_column(ForeignKey("funcionarios.id", ondelete="CASCADE"))
    perfil_id: Mapped[int] = mapped_column(ForeignKey("perfis.id", ondelete="CASCADE"))
    origem: Mapped[str] = mapped_column(String(100), default="Importacao", nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    funcionario: Mapped["Funcionario"] = relationship(back_populates="perfis")
    perfil: Mapped["Perfil"] = relationship(back_populates="funcionarios")


class PerfilAcesso(Base):
    __tablename__ = "perfil_acessos"
    __table_args__ = (
        UniqueConstraint("perfil_id", "acesso_id", name="uq_perfil_acesso"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    perfil_id: Mapped[int] = mapped_column(ForeignKey("perfis.id", ondelete="CASCADE"))
    acesso_id: Mapped[int] = mapped_column(ForeignKey("acessos.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    perfil: Mapped["Perfil"] = relationship(back_populates="acessos")
    acesso: Mapped["Acesso"] = relationship(back_populates="perfis")
'''

CRIAR = '''from sqlalchemy import inspect

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
'''

models_path = APP / 'models.py'
create_path = ROOT / 'criar_tabelas.py'
models_path.write_text(MODELS, encoding='utf-8', newline='\n')
create_path.write_text(CRIAR, encoding='utf-8', newline='\n')
py_compile.compile(str(models_path), doraise=True)
py_compile.compile(str(create_path), doraise=True)
print('Arquivos criados e validados:')
print(models_path)
print(create_path)
print(r'Agora execute: python .\criar_tabelas.py')
