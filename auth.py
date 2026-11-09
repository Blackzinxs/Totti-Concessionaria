from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)


def criar_auth_blueprint(conectar):

    auth_bp = Blueprint(
        "auth",
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
    # LOGIN
    # ========================================================

    @auth_bp.route(
        "/login",
        methods=["GET", "POST"]
    )
    def login():

        if session.get("usuario_id"):

            return redirect(
                url_for("index")
            )


        erro = None

        cadastro_sucesso = (
            request.args.get("cadastro")
            == "sucesso"
        )


        if request.method == "POST":

            email = request.form.get(
                "email",
                ""
            ).strip().lower()

            senha = request.form.get(
                "senha",
                ""
            )


            conexao = conectar()
            cursor = conexao.cursor()


            cursor.execute("""
                SELECT
                    id_usuario,
                    nome,
                    email,
                    senha,
                    perfil,
                    ativo,
                    id_cliente

                FROM usuarios

                WHERE LOWER(email) = LOWER(%s)
            """, (email,))


            usuario = cursor.fetchone()


            cursor.close()
            conexao.close()


            if not usuario:

                erro = (
                    "E-mail ou senha inválidos."
                )


            elif not usuario[5]:

                erro = (
                    "Este usuário está desativado."
                )


            elif not check_password_hash(
                usuario[3],
                senha
            ):

                erro = (
                    "E-mail ou senha inválidos."
                )


            else:

                session.clear()

                session[
                    "usuario_id"
                ] = usuario[0]

                session[
                    "usuario_nome"
                ] = usuario[1]

                session[
                    "usuario_email"
                ] = usuario[2]

                session[
                    "usuario_perfil"
                ] = usuario[4]

                session[
                    "id_cliente"
                ] = usuario[6]


                return redirect(
                    url_for("index")
                )


        return render_template(
            "login.html",
            erro=erro,
            cadastro_sucesso=cadastro_sucesso
        )


    # ========================================================
    # CADASTRO PÚBLICO DO CLIENTE
    # ========================================================

    @auth_bp.route(
        "/cadastro",
        methods=["GET", "POST"]
    )
    def cadastro():

        if session.get("usuario_id"):

            return redirect(
                url_for("index")
            )


        erro = None


        if request.method == "POST":

            tipo_pessoa = request.form.get(
                "tipo_pessoa",
                "PF"
            )


            # =================================================
            # DADOS COMUNS
            # =================================================

            telefone = vazio_para_none(
                request.form.get(
                    "telefone"
                )
            )

            email = request.form.get(
                "email",
                ""
            ).strip().lower()

            endereco = vazio_para_none(
                request.form.get(
                    "endereco"
                )
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
            # DADOS PF
            # =================================================

            nome = None
            cpf = None


            # =================================================
            # DADOS PJ
            # =================================================

            razao_social = None
            nome_fantasia = None
            cnpj = None
            inscricao_estadual = None


            # =================================================
            # PESSOA FÍSICA
            # =================================================

            if tipo_pessoa == "PF":

                nome = vazio_para_none(
                    request.form.get(
                        "nome"
                    )
                )

                cpf = vazio_para_none(
                    request.form.get(
                        "cpf"
                    )
                )


                if not nome:

                    erro = (
                        "Informe seu nome completo."
                    )


                elif not cpf:

                    erro = (
                        "Informe seu CPF."
                    )


                nome_usuario = nome


            # =================================================
            # PESSOA JURÍDICA
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
                    request.form.get(
                        "cnpj"
                    )
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
            # VALIDAÇÕES DE ACESSO
            # =================================================

            if not erro and not email:

                erro = (
                    "Informe seu e-mail."
                )


            if not erro and not senha:

                erro = (
                    "Informe uma senha."
                )


            if (
                not erro
                and len(senha) < 6
            ):

                erro = (
                    "A senha deve possuir "
                    "pelo menos 6 caracteres."
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
                    "cadastro.html",
                    erro=erro
                )


            # =================================================
            # CRIPTOGRAFAR SENHA
            # =================================================

            senha_hash = generate_password_hash(
                senha
            )


            conexao = conectar()
            cursor = conexao.cursor()


            try:

                # =============================================
                # VERIFICAR E-MAIL DE USUÁRIO
                # =============================================

                cursor.execute("""
                    SELECT id_usuario
                    FROM usuarios
                    WHERE LOWER(email) = LOWER(%s)
                """, (email,))


                if cursor.fetchone():

                    conexao.rollback()

                    cursor.close()
                    conexao.close()

                    return render_template(
                        "cadastro.html",
                        erro=(
                            "Já existe uma conta "
                            "cadastrada com este e-mail."
                        )
                    )


                # =============================================
                # VERIFICAR DOCUMENTO
                # =============================================

                if tipo_pessoa == "PF":

                    cursor.execute("""
                        SELECT id_cliente
                        FROM clientes
                        WHERE cpf = %s
                    """, (cpf,))

                    if cursor.fetchone():

                        conexao.rollback()

                        cursor.close()
                        conexao.close()

                        return render_template(
                            "cadastro.html",
                            erro=(
                                "Já existe um cadastro "
                                "com este CPF."
                            )
                        )


                else:

                    cursor.execute("""
                        SELECT id_cliente
                        FROM clientes
                        WHERE cnpj = %s
                    """, (cnpj,))

                    if cursor.fetchone():

                        conexao.rollback()

                        cursor.close()
                        conexao.close()

                        return render_template(
                            "cadastro.html",
                            erro=(
                                "Já existe um cadastro "
                                "com este CNPJ."
                            )
                        )


                # =============================================
                # CRIAR CLIENTE
                # =============================================

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


                id_cliente = (
                    cursor.fetchone()[0]
                )


                # =============================================
                # CRIAR USUÁRIO CLIENTE
                # =============================================

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


            except Exception:

                conexao.rollback()

                cursor.close()
                conexao.close()

                return render_template(
                    "cadastro.html",
                    erro=(
                        "Não foi possível concluir "
                        "o cadastro. Verifique os "
                        "dados informados."
                    )
                )


            cursor.close()
            conexao.close()


            return redirect(
                url_for(
                    "auth.login",
                    cadastro="sucesso"
                )
            )


        return render_template(
            "cadastro.html",
            erro=erro
        )


    # ========================================================
    # LOGOUT
    # ========================================================

    @auth_bp.route("/logout")
    def logout():

        session.clear()

        return redirect(
            url_for("auth.login")
        )


    return auth_bp