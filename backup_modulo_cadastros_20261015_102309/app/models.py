from datetime import datetime, timezone
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func, UniqueConstraint, Text, DateTime
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

# IMPORTACAO_E_DEPARTAMENTOS_NN_V1
class FuncionarioDepartamento(Base):
    __tablename__ = 'funcionario_departamentos'
    __table_args__ = (UniqueConstraint('funcionario_id', 'departamento_id', name='uq_funcionario_departamento'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    funcionario_id: Mapped[int] = mapped_column(ForeignKey('funcionarios.id', ondelete='CASCADE'), index=True)
    departamento_id: Mapped[int] = mapped_column(ForeignKey('departamentos.id', ondelete='CASCADE'), index=True)


class SystemUserDepartamento(Base):
    __tablename__ = 'system_user_departments'
    __table_args__ = (UniqueConstraint('system_user_id', 'departamento_id', name='uq_system_user_departamento'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    system_user_id: Mapped[int] = mapped_column(ForeignKey('system_users.id', ondelete='CASCADE'), index=True)
    departamento_id: Mapped[int] = mapped_column(ForeignKey('departamentos.id', ondelete='CASCADE'), index=True)


class ImportacaoPlanilha(Base):
    __tablename__ = 'importacoes_planilha'
    id: Mapped[int] = mapped_column(primary_key=True)
    arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    hash_arquivo: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='PROCESSANDO')
    resultado_json: Mapped[str | None] = mapped_column(Text)
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey('system_users.id', ondelete='SET NULL'))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

