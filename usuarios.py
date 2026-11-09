from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session
)

from werkzeug.security import generate_password_hash


def criar_usuarios_blueprint(conectar):

    usuarios_bp = Blueprint(
        "usuarios",
        __name__
    )


    # ========================================================
    # FUNÇÃO AUXILIAR
    # ========================================================

    def vazio_para_none(valor):

        if valor is None:
            return None

        valor = valor.strip()

        if valor == "":
            return None

        return valor


    # ========================================================
    # LISTAGEM DE USUÁRIOS
    # ========================================================

    @usuarios_bp.route("/usuarios")
    def listar_usuarios():

        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                u.id_usuario,
                u.nome,
                u.email,
                u.perfil,
                u.ativo,
                u.data_cadastro,

                COALESCE(
                    c.nome,
                    c.razao_social
                ) AS cliente

            FROM usuarios u

            LEFT JOIN clientes c
                ON u.id_cliente = c.id_cliente

            ORDER BY
                CASE
                    WHEN u.perfil = 'Superuser' THEN 1
                    WHEN u.perfil = 'Administrador' THEN 2
                    WHEN u.perfil = 'Vendedor' THEN 3
                    WHEN u.perfil = 'Cliente' THEN 4
                    ELSE 5
                END,
                u.nome
        """)

        usuarios = cursor.fetchall()

        cursor.close()
        conexao.close()

        return render_template(
            "usuarios.html",
            usuarios=usuarios
        )


    # ========================================================
    # NOVO USUÁRIO
    # CRIA CLIENTE + USUÁRIO AUTOMATICAMENTE
    # ========================================================

    @usuarios_bp.route(
        "/usuarios/novo",
        methods=["GET", "POST"]
    )
    def novo_usuario():

        erro = None

        if request.method == "POST":

            tipo_pessoa = request.form.get(
                "tipo_pessoa",
                "PF"
            )

            email = request.form.get(
                "email",
                ""
            ).strip().lower()

            telefone = vazio_para_none(
                request.form.get("telefone")
            )

            endereco = vazio_para_none(
                request.form.get("endereco")
            )

            senha = request.form.get(
                "senha",
                ""
            )

            confirmar_senha = request.form.get(
                "confirmar_senha",
                ""
            )


            # =================================================
            # CAMPOS PF
            # =================================================

            nome = None
            cpf = None


            # =================================================
            # CAMPOS PJ
            # =================================================

            razao_social = None
            nome_fantasia = None
            cnpj = None
            inscricao_estadual = None


            # =================================================
            # VALIDAÇÃO PF
            # =================================================

            if tipo_pessoa == "PF":

                nome = vazio_para_none(
                    request.form.get("nome")
                )

                cpf = vazio_para_none(
                    request.form.get("cpf")
                )

                if not nome:

                    erro = (
                        "Informe o nome completo."
                    )

                elif not cpf:

                    erro = (
                        "Informe o CPF."
                    )


                nome_usuario = nome


            # =================================================
            # VALIDAÇÃO PJ
            # =================================================

            elif tipo_pessoa == "PJ":

                razao_social = vazio_para_none(
                    request.form.get(
                        "razao_social"
                    )
                )

                nome_fantasia = vazio_para_none(
                    request.form.get(
                        "nome_fantasia"
                    )
                )

                cnpj = vazio_para_none(
                    request.form.get("cnpj")
                )

                inscricao_estadual = vazio_para_none(
                    request.form.get(
                        "inscricao_estadual"
                    )
                )


                if not razao_social:

                    erro = (
                        "Informe a razão social."
                    )

                elif not cnpj:

                    erro = (
                        "Informe o CNPJ."
                    )


                nome_usuario = (
                    nome_fantasia
                    or razao_social
                )


            else:

                erro = (
                    "Tipo de pessoa inválido."
                )

                nome_usuario = None


            # =================================================
            # VALIDAÇÃO DE ACESSO
            # =================================================

            if not erro and not email:

                erro = (
                    "Informe o e-mail."
                )


            if not erro and not senha:

                erro = (
                    "Informe uma senha."
                )


            if (
                not erro
                and senha != confirmar_senha
            ):

                erro = (
                    "As senhas não são iguais."
                )


            if erro:

                return render_template(
                    "novo_usuario.html",
                    erro=erro
                )


            # =================================================
            # CRIPTOGRAFAR SENHA
            # =================================================

            senha_hash = generate_password_hash(
                senha
            )


            # =================================================
            # TRANSAÇÃO
            # CLIENTE + USUÁRIO
            # =================================================

            conexao = conectar()
            cursor = conexao.cursor()


            try:

                # ---------------------------------------------
                # CADASTRAR CLIENTE
                # ---------------------------------------------

                cursor.execute("""
                    INSERT INTO clientes (
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
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING id_cliente
                """, (
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
                ))


                id_cliente = cursor.fetchone()[0]


                # ---------------------------------------------
                # CADASTRAR USUÁRIO
                # ---------------------------------------------

                cursor.execute("""
                    INSERT INTO usuarios (
                        nome,
                        email,
                        senha,
                        perfil,
                        ativo,
                        id_cliente
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        'Cliente',
                        TRUE,
                        %s
                    )
                """, (
                    nome_usuario,
                    email,
                    senha_hash,
                    id_cliente
                ))


                conexao.commit()


            except Exception as erro_banco:

                conexao.rollback()

                cursor.close()
                conexao.close()


                mensagem = str(
                    erro_banco
                ).lower()


                if "cpf" in mensagem:

                    erro = (
                        "Já existe um cliente "
                        "com este CPF."
                    )

                elif "cnpj" in mensagem:

                    erro = (
                        "Já existe um cliente "
                        "com este CNPJ."
                    )

                elif "email" in mensagem:

                    erro = (
                        "Já existe um usuário "
                        "com este e-mail."
                    )

                else:

                    erro = (
                        "Não foi possível realizar "
                        "o cadastro. Verifique os "
                        "dados informados."
                    )


                return render_template(
                    "novo_usuario.html",
                    erro=erro
                )


            cursor.close()
            conexao.close()


            return redirect(
                url_for(
                    "usuarios.listar_usuarios"
                )
            )


        return render_template(
            "novo_usuario.html",
            erro=erro
        )


    # ========================================================
    # EDITAR USUÁRIO
    # ========================================================

    @usuarios_bp.route(
        "/usuarios/<int:id_usuario>/editar",
        methods=["GET", "POST"]
    )
    def editar_usuario(id_usuario):

        conexao = conectar()
        cursor = conexao.cursor()


        cursor.execute("""
            SELECT
                id_usuario,
                nome,
                email,
                perfil,
                ativo,
                id_cliente

            FROM usuarios

            WHERE id_usuario = %s
        """, (id_usuario,))

        usuario_atual = cursor.fetchone()


        if not usuario_atual:

            cursor.close()
            conexao.close()

            return (
                "Usuário não encontrado.",
                404
            )


        if request.method == "POST":

            nome = request.form.get(
                "nome",
                ""
            ).strip()

            email = request.form.get(
                "email",
                ""
            ).strip().lower()

            senha = request.form.get(
                "senha",
                ""
            )

            ativo = (
                request.form.get("ativo")
                == "on"
            )


            # =================================================
            # SUPERUSER PROTEGIDO
            # =================================================

            if usuario_atual[3] == "Superuser":

                perfil = "Superuser"
                ativo = True
                id_cliente = usuario_atual[5]


            else:

                perfil = request.form.get(
                    "perfil",
                    usuario_atual[3]
                )


                if perfil not in [
                    "Administrador",
                    "Vendedor",
                    "Cliente"
                ]:

                    cursor.close()
                    conexao.close()

                    return """
                    Perfil inválido.
                    <br><br>
                    <a href="/usuarios">
                        Voltar
                    </a>
                    """


                id_cliente = usuario_atual[5]


            try:

                # =============================================
                # ATUALIZA COM NOVA SENHA
                # =============================================

                if senha:

                    senha_hash = (
                        generate_password_hash(
                            senha
                        )
                    )

                    cursor.execute("""
                        UPDATE usuarios

                        SET
                            nome = %s,
                            email = %s,
                            perfil = %s,
                            ativo = %s,
                            senha = %s

                        WHERE id_usuario = %s
                    """, (
                        nome,
                        email,
                        perfil,
                        ativo,
                        senha_hash,
                        id_usuario
                    ))


                # =============================================
                # MANTÉM SENHA ATUAL
                # =============================================

                else:

                    cursor.execute("""
                        UPDATE usuarios

                        SET
                            nome = %s,
                            email = %s,
                            perfil = %s,
                            ativo = %s

                        WHERE id_usuario = %s
                    """, (
                        nome,
                        email,
                        perfil,
                        ativo,
                        id_usuario
                    ))


                conexao.commit()


            except Exception:

                conexao.rollback()

                cursor.close()
                conexao.close()

                return """
                Não foi possível atualizar
                o usuário.
                <br><br>
                Verifique se o e-mail já
                está sendo utilizado.
                <br><br>
                <a href="/usuarios">
                    Voltar
                </a>
                """


            cursor.close()
            conexao.close()


            # =================================================
            # ATUALIZAR PRÓPRIA SESSÃO
            # =================================================

            if id_usuario == session.get(
                "usuario_id"
            ):

                session[
                    "usuario_nome"
                ] = nome

                session[
                    "usuario_email"
                ] = email

                session[
                    "usuario_perfil"
                ] = perfil

                session[
                    "id_cliente"
                ] = id_cliente


            return redirect(
                url_for(
                    "usuarios.listar_usuarios"
                )
            )


        cursor.close()
        conexao.close()


        return render_template(
            "editar_usuario.html",
            usuario=usuario_atual
        )


    # ========================================================
    # EXCLUIR USUÁRIO
    # ========================================================

    @usuarios_bp.route(
        "/usuarios/<int:id_usuario>/excluir",
        methods=["POST"]
    )
    def excluir_usuario(id_usuario):

        if id_usuario == session.get(
            "usuario_id"
        ):

            return """
            Você não pode excluir o usuário
            atualmente conectado.
            <br><br>
            <a href="/usuarios">
                Voltar
            </a>
            """


        conexao = conectar()
        cursor = conexao.cursor()


        cursor.execute("""
            SELECT
                perfil,
                id_cliente

            FROM usuarios

            WHERE id_usuario = %s
        """, (id_usuario,))

        resultado = cursor.fetchone()


        if not resultado:

            cursor.close()
            conexao.close()

            return (
                "Usuário não encontrado.",
                404
            )


        if resultado[0] == "Superuser":

            cursor.close()
            conexao.close()

            return """
            O Superuser não pode ser excluído.
            <br><br>
            <a href="/usuarios">
                Voltar
            </a>
            """


        cursor.execute("""
            DELETE FROM usuarios
            WHERE id_usuario = %s
        """, (id_usuario,))


        conexao.commit()

        cursor.close()
        conexao.close()


        return redirect(
            url_for(
                "usuarios.listar_usuarios"
            )
        )


    return usuarios_bp