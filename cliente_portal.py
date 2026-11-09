from flask import (
    Blueprint,
    render_template,
    session,
    request,
    redirect,
    url_for
)


def criar_cliente_blueprint(conectar):

    cliente_bp = Blueprint(
        "cliente_portal",
        __name__
    )


    # ========================================================
    # MINHA CONTA
    # ========================================================

    @cliente_bp.route("/minha-conta")
    def minha_conta():

        id_cliente = session.get(
            "id_cliente"
        )

        if not id_cliente:

            return (
                "Usuário não está vinculado a um cliente.",
                403
            )


        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                id_cliente,
                tipo_pessoa,
                nome,
                cpf,
                razao_social,
                nome_fantasia,
                cnpj,
                inscricao_estadual,
                telefone,
                email,
                endereco

            FROM clientes

            WHERE id_cliente = %s
        """, (id_cliente,))

        cliente = cursor.fetchone()

        cursor.close()
        conexao.close()


        if not cliente:

            return (
                "Cliente não encontrado.",
                404
            )


        return render_template(
            "minha_conta.html",
            cliente=cliente
        )


    # ========================================================
    # MINHAS COMPRAS
    # ========================================================

    @cliente_bp.route("/minhas-compras")
    def minhas_compras():

        id_cliente = session.get(
            "id_cliente"
        )

        if not id_cliente:

            return (
                "Usuário não está vinculado a um cliente.",
                403
            )


        conexao = conectar()
        cursor = conexao.cursor()


        cursor.execute("""
            SELECT
                ve.id_venda,
                ve.data_venda,
                ma.nome AS marca,
                mo.nome AS modelo,
                v.placa,
                v.ano_modelo,
                v.cor,
                ve.valor_venda,
                ve.forma_pagamento,
                vd.nome AS vendedor

            FROM vendas ve

            INNER JOIN veiculos v
                ON ve.id_veiculo = v.id_veiculo

            INNER JOIN modelos mo
                ON v.id_modelo = mo.id_modelo

            INNER JOIN marcas ma
                ON mo.id_marca = ma.id_marca

            INNER JOIN vendedores vd
                ON ve.id_vendedor = vd.id_vendedor

            WHERE ve.id_cliente = %s

            ORDER BY
                ve.data_venda DESC,
                ve.id_venda DESC
        """, (id_cliente,))

        compras = cursor.fetchall()

        cursor.close()
        conexao.close()


        return render_template(
            "minhas_compras.html",
            compras=compras
        )


    # ========================================================
    # COMPRAR VEÍCULO
    # ========================================================

    @cliente_bp.route(
        "/comprar/<int:id_veiculo>",
        methods=["GET", "POST"]
    )
    def comprar_veiculo(id_veiculo):

        # ====================================================
        # SOMENTE CLIENTE
        # ====================================================

        if session.get(
            "usuario_perfil"
        ) != "Cliente":

            return (
                "Acesso não autorizado.",
                403
            )


        id_cliente = session.get(
            "id_cliente"
        )


        if not id_cliente:

            return (
                "Usuário não está vinculado a um cliente.",
                403
            )


        conexao = conectar()
        cursor = conexao.cursor()


        try:

            # =================================================
            # BUSCAR VEÍCULO
            # =================================================

            cursor.execute("""
                SELECT
                    v.id_veiculo,
                    ma.nome,
                    mo.nome,
                    v.ano_modelo,
                    v.cor,
                    v.quilometragem,
                    v.preco_venda,
                    v.status,
                    v.placa

                FROM veiculos v

                INNER JOIN modelos mo
                    ON v.id_modelo = mo.id_modelo

                INNER JOIN marcas ma
                    ON mo.id_marca = ma.id_marca

                WHERE v.id_veiculo = %s
            """, (id_veiculo,))


            veiculo = cursor.fetchone()


            if not veiculo:

                cursor.close()
                conexao.close()

                return (
                    "Veículo não encontrado.",
                    404
                )


            # =================================================
            # VEÍCULO JÁ VENDIDO
            # =================================================

            if veiculo[7] != "Disponível":

                cursor.close()
                conexao.close()

                return render_template(
                    "compra_indisponivel.html",
                    veiculo=veiculo
                )


            # =================================================
            # FORMAS DE PAGAMENTO
            # =================================================

            cursor.execute("""
                SELECT descricao
                FROM formas_pagamento
                ORDER BY id_forma_pagamento
            """)

            formas_pagamento = [
                linha[0]
                for linha in cursor.fetchall()
            ]


            # =================================================
            # GET - MOSTRAR CONFIRMAÇÃO
            # =================================================

            if request.method == "GET":

                cursor.close()
                conexao.close()

                return render_template(
                    "comprar_veiculo.html",
                    veiculo=veiculo,
                    formas_pagamento=formas_pagamento,
                    erro=None
                )


            # =================================================
            # POST - EFETUAR COMPRA
            # =================================================

            forma_pagamento = request.form.get(
                "forma_pagamento",
                ""
            ).strip()


            if forma_pagamento not in formas_pagamento:

                cursor.close()
                conexao.close()

                return render_template(
                    "comprar_veiculo.html",
                    veiculo=veiculo,
                    formas_pagamento=formas_pagamento,
                    erro="Selecione uma forma de pagamento válida."
                )


            # =================================================
            # BLOQUEAR VEÍCULO DURANTE A TRANSAÇÃO
            # =================================================

            cursor.execute("""
                SELECT
                    status,
                    preco_venda

                FROM veiculos

                WHERE id_veiculo = %s

                FOR UPDATE
            """, (id_veiculo,))


            veiculo_bloqueado = (
                cursor.fetchone()
            )


            if not veiculo_bloqueado:

                conexao.rollback()

                cursor.close()
                conexao.close()

                return (
                    "Veículo não encontrado.",
                    404
                )


            if (
                veiculo_bloqueado[0]
                != "Disponível"
            ):

                conexao.rollback()

                cursor.close()
                conexao.close()

                return render_template(
                    "compra_indisponivel.html",
                    veiculo=veiculo
                )


            valor_venda = (
                veiculo_bloqueado[1]
            )


            if valor_venda is None:

                conexao.rollback()

                cursor.close()
                conexao.close()

                return render_template(
                    "comprar_veiculo.html",
                    veiculo=veiculo,
                    formas_pagamento=formas_pagamento,
                    erro=(
                        "Este veículo ainda não possui "
                        "preço de venda cadastrado."
                    )
                )


            # =================================================
            # LOCALIZAR VENDEDOR ONLINE
            # =================================================

            cursor.execute("""
                SELECT id_vendedor

                FROM vendedores

                WHERE email = %s
            """, (
                "vendaonline@totti.com.br",
            ))


            vendedor_online = (
                cursor.fetchone()
            )


            if not vendedor_online:

                conexao.rollback()

                cursor.close()
                conexao.close()

                return (
                    """
                    O vendedor Venda Online não foi encontrado.
                    Verifique o cadastro do vendedor no sistema.
                    """,
                    500
                )


            id_vendedor = (
                vendedor_online[0]
            )


            # =================================================
            # REGISTRAR VENDA
            # =================================================

            cursor.execute("""
                INSERT INTO vendas (
                    id_cliente,
                    id_vendedor,
                    id_veiculo,
                    valor_venda,
                    forma_pagamento,
                    observacoes
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                id_cliente,
                id_vendedor,
                id_veiculo,
                valor_venda,
                forma_pagamento,
                "Compra realizada pelo Portal do Cliente."
            ))


            # =================================================
            # ALTERAR STATUS DO VEÍCULO
            # =================================================

            cursor.execute("""
                UPDATE veiculos

                SET status = 'Vendido'

                WHERE id_veiculo = %s
            """, (id_veiculo,))


            conexao.commit()


        except Exception as erro:

            conexao.rollback()

            cursor.close()
            conexao.close()

            return (
                f"""
                Não foi possível concluir a compra.
                <br><br>
                Erro: {erro}
                <br><br>
                <a href="/">Voltar</a>
                """,
                500
            )


        cursor.close()
        conexao.close()


        return redirect(
            url_for(
                "cliente_portal.compra_sucesso"
            )
        )


    # ========================================================
    # COMPRA REALIZADA
    # ========================================================

    @cliente_bp.route(
        "/compra-realizada"
    )
    def compra_sucesso():

        if session.get(
            "usuario_perfil"
        ) != "Cliente":

            return (
                "Acesso não autorizado.",
                403
            )


        return render_template(
            "compra_sucesso.html"
        )


    return cliente_bp