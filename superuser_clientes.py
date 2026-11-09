from flask import (
    Blueprint,
    redirect,
    url_for,
    session
)


def criar_superuser_clientes_blueprint(conectar):

    superuser_clientes_bp = Blueprint(
        "superuser_clientes",
        __name__
    )


    # ========================================================
    # EXCLUSÃO DEFINITIVA DE CLIENTE
    # SOMENTE SUPERUSER
    # ========================================================

    @superuser_clientes_bp.route(
        "/clientes/<int:id_cliente>/excluir-definitivamente",
        methods=["POST"]
    )
    def excluir_cliente_definitivamente(id_cliente):

        # Segurança adicional dentro da própria rota
        if session.get("usuario_perfil") != "Superuser":

            return (
                """
                Acesso não autorizado.
                <br><br>
                Somente o Superuser pode excluir
                clientes definitivamente.
                <br><br>
                <a href="/clientes">Voltar</a>
                """,
                403
            )


        conexao = conectar()
        cursor = conexao.cursor()


        try:

            # =================================================
            # VERIFICAR SE O CLIENTE EXISTE
            # =================================================

            cursor.execute("""
                SELECT
                    id_cliente,
                    COALESCE(
                        nome,
                        razao_social
                    )
                FROM clientes
                WHERE id_cliente = %s
            """, (id_cliente,))

            cliente = cursor.fetchone()


            if not cliente:

                cursor.close()
                conexao.close()

                return (
                    "Cliente não encontrado.",
                    404
                )


            # =================================================
            # IDENTIFICAR VEÍCULOS DAS VENDAS
            # =================================================

            cursor.execute("""
                SELECT id_veiculo
                FROM vendas
                WHERE id_cliente = %s
            """, (id_cliente,))

            veiculos_vendidos = cursor.fetchall()


            # =================================================
            # EXCLUIR LOGIN/USUÁRIO DO CLIENTE
            # =================================================

            cursor.execute("""
                DELETE FROM usuarios
                WHERE id_cliente = %s
            """, (id_cliente,))


            # =================================================
            # EXCLUIR VENDAS DO CLIENTE
            # =================================================

            cursor.execute("""
                DELETE FROM vendas
                WHERE id_cliente = %s
            """, (id_cliente,))


            # =================================================
            # DEVOLVER VEÍCULOS PARA DISPONÍVEL
            # =================================================

            for veiculo in veiculos_vendidos:

                cursor.execute("""
                    UPDATE veiculos
                    SET status = 'Disponível'
                    WHERE id_veiculo = %s
                """, (veiculo[0],))


            # =================================================
            # EXCLUIR CLIENTE
            # =================================================

            cursor.execute("""
                DELETE FROM clientes
                WHERE id_cliente = %s
            """, (id_cliente,))


            conexao.commit()


        except Exception as erro:

            conexao.rollback()

            cursor.close()
            conexao.close()

            return f"""
            Não foi possível excluir definitivamente
            o cliente.
            <br><br>
            Erro: {erro}
            <br><br>
            <a href="/clientes">Voltar</a>
            """


        cursor.close()
        conexao.close()


        return redirect(
            url_for("clientes")
        )


    return superuser_clientes_bp