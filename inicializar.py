import os

from flask import (
    request,
    redirect,
    url_for,
    session,
    render_template
)

from app import app, conectar

from auth import (
    criar_auth_blueprint
)

from usuarios import (
    criar_usuarios_blueprint
)

from cliente_portal import (
    criar_cliente_blueprint
)

from superuser_clientes import (
    criar_superuser_clientes_blueprint
)


# ============================================================
# SEGURANÇA DA SESSÃO
# ============================================================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "totti-concessionaria-chave-local"
)


# ============================================================
# AUTENTICAÇÃO
# ============================================================

auth_bp = criar_auth_blueprint(
    conectar
)

app.register_blueprint(
    auth_bp
)


# ============================================================
# USUÁRIOS
# ============================================================

usuarios_bp = criar_usuarios_blueprint(
    conectar
)

app.register_blueprint(
    usuarios_bp
)


# ============================================================
# PORTAL DO CLIENTE
# ============================================================

cliente_bp = criar_cliente_blueprint(
    conectar
)

app.register_blueprint(
    cliente_bp
)


# ============================================================
# FUNÇÕES DO SUPERUSER
# ============================================================

superuser_clientes_bp = (
    criar_superuser_clientes_blueprint(
        conectar
    )
)

app.register_blueprint(
    superuser_clientes_bp
)


# ============================================================
# ROTAS DO VENDEDOR
# ============================================================

ROTAS_VENDEDOR = {

    "index",
    "visualizar_veiculo",

    "clientes",
    "novo_cliente",
    "editar_cliente",

    "vendas",
    "nova_venda",

    "auth.logout"
}


# ============================================================
# ROTAS DO CLIENTE
# ============================================================

ROTAS_CLIENTE = {

    "index",

    "visualizar_veiculo",

    "cliente_portal.minha_conta",

    "cliente_portal.minhas_compras",

    "cliente_portal.comprar_veiculo",

    "cliente_portal.compra_sucesso",

    "auth.logout"
}


# ============================================================
# CONTROLE DE ACESSO
# ============================================================

@app.before_request
def controlar_acesso():

    endpoint = request.endpoint


    if endpoint is None:

        return None


    # ========================================================
    # ROTAS PÚBLICAS
    # ========================================================

    rotas_publicas = {

        "auth.login",

        "auth.cadastro",

        "static"
    }


    if endpoint in rotas_publicas:

        return None


    # ========================================================
    # EXIGIR LOGIN
    # ========================================================

    if not session.get(
        "usuario_id"
    ):

        return redirect(
            url_for(
                "auth.login"
            )
        )


    perfil = session.get(
        "usuario_perfil"
    )


    # ========================================================
    # SUPERUSER
    # ========================================================

    if perfil == "Superuser":

        return None


    # ========================================================
    # ADMINISTRADOR
    # ========================================================

    if perfil == "Administrador":

        if endpoint.startswith(
            "usuarios."
        ):

            return (
                render_template(
                    "acesso_negado.html"
                ),
                403
            )


        if endpoint == "excluir_cliente":

            return (
                render_template(
                    "acesso_negado.html"
                ),
                403
            )


        if endpoint.startswith(
            "superuser_clientes."
        ):

            return (
                render_template(
                    "acesso_negado.html"
                ),
                403
            )


        return None


    # ========================================================
    # VENDEDOR
    # ========================================================

    if perfil == "Vendedor":

        if endpoint in ROTAS_VENDEDOR:

            return None


        return (
            render_template(
                "acesso_negado.html"
            ),
            403
        )


    # ========================================================
    # CLIENTE
    # ========================================================

    if perfil == "Cliente":

        if endpoint in ROTAS_CLIENTE:

            return None


        return (
            render_template(
                "acesso_negado.html"
            ),
            403
        )


    # ========================================================
    # PERFIL INVÁLIDO
    # ========================================================

    session.clear()

    return redirect(
        url_for(
            "auth.login"
        )
    )


# ============================================================
# INICIAR SISTEMA
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )