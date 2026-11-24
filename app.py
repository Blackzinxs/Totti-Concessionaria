from flask import Flask, render_template, request, redirect, url_for, session, abort
from werkzeug.utils import secure_filename
import psycopg2
import os
import uuid
import secrets


app = Flask(__name__)
# No ambiente de produção, a SECRET_KEY deve permanecer estável.
# Configure-a em Vercel > Project Settings > Environment Variables.
if os.environ.get("VERCEL") and not os.environ.get("SECRET_KEY"):
    raise RuntimeError("Configure SECRET_KEY nas variáveis de ambiente da Vercel")
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("RENDER") or os.environ.get("VERCEL"):
    app.config["SESSION_COOKIE_SECURE"] = True


# ============================================================
# UPLOAD DE IMAGENS DOS VEÍCULOS
# ============================================================

PASTA_IMAGENS_VEICULOS = os.path.join(
    app.root_path,
    "static",
    "veiculos"
)

EXTENSOES_IMAGEM_PERMITIDAS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}

# Na Vercel, o código do deploy é somente leitura. Não tente criar
# pastas em static durante a inicialização do app.
if not os.environ.get("VERCEL"):
    os.makedirs(PASTA_IMAGENS_VEICULOS, exist_ok=True)

# Limite máximo de 8 MB por arquivo enviado.
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


# ============================================================
# CONEXÃO COM O POSTGRESQL
# ============================================================

def conectar():
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        return psycopg2.connect(database_url)

    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        database=os.getenv("PGDATABASE", "concessionaria"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD", ""),
        port=os.getenv("PGPORT", "5432")
    )


def vazio_para_none(valor):
    if valor is None:
        return None

    valor = valor.strip()

    if valor == "":
        return None

    return valor


def salvar_imagem_veiculo(arquivo):
    # Upload persistente precisa de storage externo (S3, R2 etc.).
    if os.environ.get("VERCEL") and arquivo is not None and arquivo.filename:
        raise ValueError("Upload de fotos indisponível na Vercel até configurar armazenamento externo.")
    if arquivo is None or arquivo.filename == "":
        return None

    nome_original = secure_filename(arquivo.filename)

    if "." not in nome_original:
        raise ValueError("Arquivo de imagem sem extensão.")

    extensao = nome_original.rsplit(".", 1)[1].lower()

    if extensao not in EXTENSOES_IMAGEM_PERMITIDAS:
        raise ValueError(
            "Formato de imagem inválido. "
            "Use PNG, JPG, JPEG ou WEBP."
        )

    nome_arquivo = (
        f"{uuid.uuid4().hex}.{extensao}"
    )

    caminho = os.path.join(
        PASTA_IMAGENS_VEICULOS,
        nome_arquivo
    )

    arquivo.save(caminho)

    return nome_arquivo


def excluir_imagem_veiculo(nome_arquivo):
    if not nome_arquivo:
        return

    caminho = os.path.join(
        PASTA_IMAGENS_VEICULOS,
        nome_arquivo
    )

    if os.path.isfile(caminho):
        os.remove(caminho)


# ============================================================
# VEÍCULOS - LISTAGEM E PESQUISA
# ============================================================

@app.route("/", methods=["GET"])
def index():

    placa = request.args.get("placa", "").strip()
    renavam = request.args.get("renavam", "").strip()
    chassi = request.args.get("chassi", "").strip()
    marca = request.args.get("marca", "").strip()
    modelo = request.args.get("modelo", "").strip()
    cor = request.args.get("cor", "").strip()
    status = request.args.get("status", "").strip()

    conexao = conectar()
    cursor = conexao.cursor()

    sql = """
        SELECT
            v.id_veiculo,
            v.placa,
            v.renavam,
            v.chassi,
            ma.nome AS marca,
            mo.nome AS modelo,
            v.ano_modelo,
            v.cor,
            v.quilometragem,
            v.preco_venda,
            v.status,
            v.imagem

        FROM veiculos v

        INNER JOIN modelos mo
            ON v.id_modelo = mo.id_modelo

        INNER JOIN marcas ma
            ON mo.id_marca = ma.id_marca

        WHERE 1 = 1
    """

    parametros = []

    if placa:
        sql += " AND v.placa ILIKE %s"
        parametros.append(f"%{placa}%")

    if renavam:
        sql += " AND v.renavam ILIKE %s"
        parametros.append(f"%{renavam}%")

    if chassi:
        sql += " AND v.chassi ILIKE %s"
        parametros.append(f"%{chassi}%")

    if marca:
        sql += " AND ma.nome ILIKE %s"
        parametros.append(f"%{marca}%")

    if modelo:
        sql += " AND mo.nome ILIKE %s"
        parametros.append(f"%{modelo}%")

    if cor:
        sql += " AND v.cor ILIKE %s"
        parametros.append(f"%{cor}%")

    if status:
        sql += " AND v.status ILIKE %s"
        parametros.append(f"%{status}%")

    sql += " ORDER BY ma.nome, mo.nome"

    cursor.execute(sql, parametros)
    veiculos = cursor.fetchall()

    cursor.execute("""
        SELECT nome
        FROM marcas
        ORDER BY nome
    """)
    marcas = cursor.fetchall()

    cursor.execute("""
        SELECT nome
        FROM modelos
        ORDER BY nome
    """)
    modelos = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT cor
        FROM veiculos
        WHERE cor IS NOT NULL
        ORDER BY cor
    """)
    cores = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT status
        FROM veiculos
        WHERE status IS NOT NULL
        ORDER BY status
    """)
    status_lista = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template(
        "index.html",
        veiculos=veiculos,
        marcas=marcas,
        modelos=modelos,
        cores=cores,
        status_lista=status_lista,
        placa=placa,
        renavam=renavam,
        chassi=chassi,
        marca=marca,
        modelo=modelo,
        cor=cor,
        status=status
    )


# ============================================================
# VEÍCULOS - CADASTRO
# ============================================================

@app.route("/veiculos/novo", methods=["GET", "POST"])
def novo_veiculo():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            mo.id_modelo,
            ma.nome,
            mo.nome
        FROM modelos mo
        INNER JOIN marcas ma
            ON mo.id_marca = ma.id_marca
        ORDER BY ma.nome, mo.nome
    """)

    modelos = cursor.fetchall()

    if request.method == "POST":

        placa = request.form["placa"].strip().upper()
        chassi = request.form["chassi"].strip().upper()
        renavam = request.form["renavam"].strip()
        id_modelo = request.form["id_modelo"]
        ano_fabricacao = request.form["ano_fabricacao"]
        ano_modelo = request.form["ano_modelo"]
        cor = request.form["cor"].strip()
        combustivel = request.form["combustivel"]
        cambio = request.form["cambio"]
        quilometragem = request.form["quilometragem"]

        numero_motor = vazio_para_none(
            request.form.get("numero_motor")
        )

        preco_venda = request.form["preco_venda"]
        status = request.form["status"]

        observacoes = vazio_para_none(
            request.form.get("observacoes")
        )

        arquivo_imagem = request.files.get(
            "imagem"
        )

        imagem = None

        try:

            imagem = salvar_imagem_veiculo(
                arquivo_imagem
            )

            cursor.execute("""
                INSERT INTO veiculos (
                    placa,
                    chassi,
                    renavam,
                    id_modelo,
                    ano_fabricacao,
                    ano_modelo,
                    cor,
                    combustivel,
                    cambio,
                    quilometragem,
                    numero_motor,
                    preco_venda,
                    status,
                    observacoes,
                    imagem
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
            """, (
                placa,
                chassi,
                renavam,
                id_modelo,
                ano_fabricacao,
                ano_modelo,
                cor,
                combustivel,
                cambio,
                quilometragem,
                numero_motor,
                preco_venda,
                status,
                observacoes,
                imagem
            ))

            conexao.commit()

        except Exception as erro:

            conexao.rollback()

            if imagem:
                excluir_imagem_veiculo(
                    imagem
                )

            cursor.close()
            conexao.close()

            return f"""
            Não foi possível cadastrar o veículo.
            <br><br>
            Verifique os dados informados e a imagem selecionada.
            <br><br>
            Erro: {erro}
            <br><br>
            <a href="/veiculos/novo">Voltar</a>
            """

        cursor.close()
        conexao.close()

        return redirect(
            url_for("index")
        )

    cursor.close()
    conexao.close()

    return render_template(
        "novo_veiculo.html",
        modelos=modelos
    )


# ============================================================
# VEÍCULOS - VISUALIZAÇÃO
# ============================================================

@app.route("/veiculos/<int:id_veiculo>")
def visualizar_veiculo(id_veiculo):

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            v.id_veiculo,
            v.placa,
            v.renavam,
            v.chassi,
            ma.nome,
            mo.nome,
            v.ano_fabricacao,
            v.ano_modelo,
            v.cor,
            v.combustivel,
            v.cambio,
            v.quilometragem,
            v.numero_motor,
            v.preco_venda,
            v.status,
            v.data_entrada,
            v.observacoes,
            v.imagem

        FROM veiculos v

        INNER JOIN modelos mo
            ON v.id_modelo = mo.id_modelo

        INNER JOIN marcas ma
            ON mo.id_marca = ma.id_marca

        WHERE v.id_veiculo = %s
    """, (id_veiculo,))

    veiculo = cursor.fetchone()

    cursor.close()
    conexao.close()

    if not veiculo:
        return "Veículo não encontrado.", 404

    return render_template(
        "visualizar_veiculo.html",
        veiculo=veiculo
    )


# ============================================================
# VEÍCULOS - EDIÇÃO
# ============================================================

@app.route(
    "/veiculos/<int:id_veiculo>/editar",
    methods=["GET", "POST"]
)
def editar_veiculo(id_veiculo):

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            mo.id_modelo,
            ma.nome,
            mo.nome

        FROM modelos mo

        INNER JOIN marcas ma
            ON mo.id_marca = ma.id_marca

        ORDER BY ma.nome, mo.nome
    """)

    modelos = cursor.fetchall()

    if request.method == "POST":

        placa = request.form["placa"].strip().upper()
        chassi = request.form["chassi"].strip().upper()
        renavam = request.form["renavam"].strip()
        id_modelo = request.form["id_modelo"]
        ano_fabricacao = request.form["ano_fabricacao"]
        ano_modelo = request.form["ano_modelo"]
        cor = request.form["cor"].strip()
        combustivel = request.form["combustivel"]
        cambio = request.form["cambio"]
        quilometragem = request.form["quilometragem"]

        numero_motor = vazio_para_none(
            request.form.get("numero_motor")
        )

        preco_venda = request.form["preco_venda"]
        status = request.form["status"]

        observacoes = vazio_para_none(
            request.form.get("observacoes")
        )

        cursor.execute("""
            SELECT imagem
            FROM veiculos
            WHERE id_veiculo = %s
        """, (id_veiculo,))

        resultado_imagem = cursor.fetchone()

        if not resultado_imagem:
            cursor.close()
            conexao.close()
            return "Veículo não encontrado.", 404

        imagem_atual = resultado_imagem[0]

        arquivo_imagem = request.files.get(
            "imagem"
        )

        nova_imagem = None
        imagem_final = imagem_atual

        try:

            if (
                arquivo_imagem
                and arquivo_imagem.filename
            ):

                nova_imagem = (
                    salvar_imagem_veiculo(
                        arquivo_imagem
                    )
                )

                imagem_final = nova_imagem

            cursor.execute("""
                UPDATE veiculos
                SET
                    placa = %s,
                    chassi = %s,
                    renavam = %s,
                    id_modelo = %s,
                    ano_fabricacao = %s,
                    ano_modelo = %s,
                    cor = %s,
                    combustivel = %s,
                    cambio = %s,
                    quilometragem = %s,
                    numero_motor = %s,
                    preco_venda = %s,
                    status = %s,
                    observacoes = %s,
                    imagem = %s

                WHERE id_veiculo = %s
            """, (
                placa,
                chassi,
                renavam,
                id_modelo,
                ano_fabricacao,
                ano_modelo,
                cor,
                combustivel,
                cambio,
                quilometragem,
                numero_motor,
                preco_venda,
                status,
                observacoes,
                imagem_final,
                id_veiculo
            ))

            conexao.commit()

            if (
                nova_imagem
                and imagem_atual
                and imagem_atual != nova_imagem
            ):

                excluir_imagem_veiculo(
                    imagem_atual
                )

        except Exception as erro:

            conexao.rollback()

            if nova_imagem:
                excluir_imagem_veiculo(
                    nova_imagem
                )

            cursor.close()
            conexao.close()

            return f"""
            Não foi possível atualizar o veículo.
            <br><br>
            Verifique os dados e a imagem selecionada.
            <br><br>
            Erro: {erro}
            <br><br>
            <a href="/veiculos/{id_veiculo}/editar">
                Voltar
            </a>
            """

        cursor.close()
        conexao.close()

        return redirect(
            url_for("index")
        )

    cursor.execute("""
        SELECT
            id_veiculo,
            placa,
            chassi,
            renavam,
            id_modelo,
            ano_fabricacao,
            ano_modelo,
            cor,
            combustivel,
            cambio,
            quilometragem,
            numero_motor,
            preco_venda,
            status,
            observacoes,
            imagem

        FROM veiculos

        WHERE id_veiculo = %s
    """, (id_veiculo,))

    veiculo = cursor.fetchone()

    cursor.close()
    conexao.close()

    if not veiculo:
        return "Veículo não encontrado.", 404

    return render_template(
        "editar_veiculo.html",
        veiculo=veiculo,
        modelos=modelos
    )


# ============================================================
# VEÍCULOS - EXCLUSÃO
# ============================================================

@app.route(
    "/veiculos/<int:id_veiculo>/excluir",
    methods=["POST"]
)
def excluir_veiculo(id_veiculo):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        cursor.execute("""
            SELECT imagem
            FROM veiculos
            WHERE id_veiculo = %s
        """, (id_veiculo,))

        resultado = cursor.fetchone()

        imagem = (
            resultado[0]
            if resultado
            else None
        )

        cursor.execute("""
            DELETE FROM veiculos
            WHERE id_veiculo = %s
        """, (id_veiculo,))

        conexao.commit()

        if imagem:
            excluir_imagem_veiculo(
                imagem
            )

    except Exception as erro:

        conexao.rollback()

        cursor.close()
        conexao.close()

        return f"""
        Não foi possível excluir o veículo.
        <br><br>
        O veículo pode possuir venda,
        manutenção ou histórico vinculado.
        <br><br>
        Erro: {erro}
        <br><br>
        <a href="/">Voltar</a>
        """

    cursor.close()
    conexao.close()

    return redirect(url_for("index"))


# ============================================================
# CLIENTES - LISTAGEM E PESQUISA
# ============================================================

@app.route("/clientes", methods=["GET"])
def clientes():

    busca = request.args.get("busca", "").strip()

    conexao = conectar()
    cursor = conexao.cursor()

    sql = """
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

        WHERE 1 = 1
    """

    parametros = []

    if busca:

        termo = f"%{busca}%"

        sql += """
            AND (
                nome ILIKE %s
                OR cpf ILIKE %s
                OR razao_social ILIKE %s
                OR nome_fantasia ILIKE %s
                OR cnpj ILIKE %s
            )
        """

        parametros.extend([
            termo,
            termo,
            termo,
            termo,
            termo
        ])

    sql += """
        ORDER BY COALESCE(nome, razao_social)
    """

    cursor.execute(sql, parametros)

    clientes = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template(
        "clientes.html",
        clientes=clientes,
        busca=busca
    )


# ============================================================
# CLIENTES - CADASTRO
# ============================================================

@app.route("/clientes/novo", methods=["GET", "POST"])
def novo_cliente():

    if request.method == "POST":

        tipo_pessoa = request.form["tipo_pessoa"]

        telefone = vazio_para_none(
            request.form.get("telefone")
        )

        email = vazio_para_none(
            request.form.get("email")
        )

        endereco = vazio_para_none(
            request.form.get("endereco")
        )

        nome = None
        cpf = None
        razao_social = None
        nome_fantasia = None
        cnpj = None
        inscricao_estadual = None

        if tipo_pessoa == "PF":

            nome = vazio_para_none(
                request.form.get("nome")
            )

            cpf = vazio_para_none(
                request.form.get("cpf")
            )

        elif tipo_pessoa == "PJ":

            razao_social = vazio_para_none(
                request.form.get("razao_social")
            )

            nome_fantasia = vazio_para_none(
                request.form.get("nome_fantasia")
            )

            cnpj = vazio_para_none(
                request.form.get("cnpj")
            )

            inscricao_estadual = vazio_para_none(
                request.form.get("inscricao_estadual")
            )

        conexao = conectar()
        cursor = conexao.cursor()

        try:

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
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
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

            conexao.commit()

        except Exception as erro:

            conexao.rollback()

            cursor.close()
            conexao.close()

            return f"""
            Não foi possível cadastrar o cliente.
            <br><br>
            Verifique se o CPF ou CNPJ já está cadastrado.
            <br><br>
            Erro: {erro}
            <br><br>
            <a href="/clientes/novo">Voltar</a>
            """

        cursor.close()
        conexao.close()

        return redirect(url_for("clientes"))

    return render_template("novo_cliente.html")


# ============================================================
# CLIENTES - EDIÇÃO
# ============================================================

@app.route(
    "/clientes/<int:id_cliente>/editar",
    methods=["GET", "POST"]
)
def editar_cliente(id_cliente):

    conexao = conectar()
    cursor = conexao.cursor()

    if request.method == "POST":

        tipo_pessoa = request.form["tipo_pessoa"]

        telefone = vazio_para_none(
            request.form.get("telefone")
        )

        email = vazio_para_none(
            request.form.get("email")
        )

        endereco = vazio_para_none(
            request.form.get("endereco")
        )

        nome = None
        cpf = None
        razao_social = None
        nome_fantasia = None
        cnpj = None
        inscricao_estadual = None

        if tipo_pessoa == "PF":

            nome = vazio_para_none(
                request.form.get("nome")
            )

            cpf = vazio_para_none(
                request.form.get("cpf")
            )

        elif tipo_pessoa == "PJ":

            razao_social = vazio_para_none(
                request.form.get("razao_social")
            )

            nome_fantasia = vazio_para_none(
                request.form.get("nome_fantasia")
            )

            cnpj = vazio_para_none(
                request.form.get("cnpj")
            )

            inscricao_estadual = vazio_para_none(
                request.form.get("inscricao_estadual")
            )

        try:

            cursor.execute("""
                UPDATE clientes
                SET
                    tipo_pessoa = %s,
                    nome = %s,
                    cpf = %s,
                    razao_social = %s,
                    nome_fantasia = %s,
                    cnpj = %s,
                    inscricao_estadual = %s,
                    telefone = %s,
                    email = %s,
                    endereco = %s

                WHERE id_cliente = %s
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
                endereco,
                id_cliente
            ))

            conexao.commit()

        except Exception as erro:

            conexao.rollback()

            cursor.close()
            conexao.close()

            return f"""
            Não foi possível atualizar o cliente.
            <br><br>
            Verifique se o CPF ou CNPJ
            já pertence a outro cadastro.
            <br><br>
            Erro: {erro}
            <br><br>
            <a href="/clientes/{id_cliente}/editar">
                Voltar
            </a>
            """

        cursor.close()
        conexao.close()

        return redirect(url_for("clientes"))

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
        return "Cliente não encontrado.", 404

    return render_template(
        "editar_cliente.html",
        cliente=cliente
    )


# ============================================================
# CLIENTES - EXCLUSÃO
# ============================================================

@app.route(
    "/clientes/<int:id_cliente>/excluir",
    methods=["POST"]
)
def excluir_cliente(id_cliente):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

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
        Não foi possível excluir o cliente.
        <br><br>
        Esse cliente pode possuir uma venda vinculada.
        <br><br>
        Erro: {erro}
        <br><br>
        <a href="/clientes">Voltar</a>
        """

    cursor.close()
    conexao.close()

    return redirect(url_for("clientes"))


# ============================================================
# VENDEDORES - LISTAGEM E PESQUISA
# ============================================================

@app.route("/vendedores", methods=["GET"])
def vendedores():

    busca = request.args.get("busca", "").strip()

    conexao = conectar()
    cursor = conexao.cursor()

    sql = """
        SELECT
            id_vendedor,
            nome,
            cpf,
            telefone,
            email

        FROM vendedores

        WHERE 1 = 1
    """

    parametros = []

    if busca:

        termo = f"%{busca}%"

        sql += """
            AND (
                nome ILIKE %s
                OR cpf ILIKE %s
                OR telefone ILIKE %s
                OR email ILIKE %s
            )
        """

        parametros.extend([
            termo,
            termo,
            termo,
            termo
        ])

    sql += " ORDER BY nome"

    cursor.execute(sql, parametros)

    vendedores = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template(
        "vendedores.html",
        vendedores=vendedores,
        busca=busca
    )


# ============================================================
# VENDEDORES - CADASTRO
# ============================================================

@app.route("/vendedores/novo", methods=["GET", "POST"])
def novo_vendedor():

    if request.method == "POST":

        nome = request.form["nome"].strip()
        cpf = request.form["cpf"].strip()

        telefone = vazio_para_none(
            request.form.get("telefone")
        )

        email = vazio_para_none(
            request.form.get("email")
        )

        conexao = conectar()
        cursor = conexao.cursor()

        try:

            cursor.execute("""
                INSERT INTO vendedores (
                    nome,
                    cpf,
                    telefone,
                    email
                )
                VALUES (%s, %s, %s, %s)
            """, (
                nome,
                cpf,
                telefone,
                email
            ))

            conexao.commit()

        except Exception as erro:

            conexao.rollback()

            cursor.close()
            conexao.close()

            return f"""
            Não foi possível cadastrar o vendedor.
            <br><br>
            Verifique se o CPF já está cadastrado.
            <br><br>
            Erro: {erro}
            <br><br>
            <a href="/vendedores/novo">Voltar</a>
            """

        cursor.close()
        conexao.close()

        return redirect(url_for("vendedores"))

    return render_template("novo_vendedor.html")


# ============================================================
# VENDEDORES - EDIÇÃO
# ============================================================

@app.route(
    "/vendedores/<int:id_vendedor>/editar",
    methods=["GET", "POST"]
)
def editar_vendedor(id_vendedor):

    conexao = conectar()
    cursor = conexao.cursor()

    if request.method == "POST":

        nome = request.form["nome"].strip()
        cpf = request.form["cpf"].strip()

        telefone = vazio_para_none(
            request.form.get("telefone")
        )

        email = vazio_para_none(
            request.form.get("email")
        )

        try:

            cursor.execute("""
                UPDATE vendedores
                SET
                    nome = %s,
                    cpf = %s,
                    telefone = %s,
                    email = %s

                WHERE id_vendedor = %s
            """, (
                nome,
                cpf,
                telefone,
                email,
                id_vendedor
            ))

            conexao.commit()

        except Exception as erro:

            conexao.rollback()

            cursor.close()
            conexao.close()

            return f"""
            Não foi possível atualizar o vendedor.
            <br><br>
            Erro: {erro}
            <br><br>
            <a href="/vendedores/{id_vendedor}/editar">
                Voltar
            </a>
            """

        cursor.close()
        conexao.close()

        return redirect(url_for("vendedores"))

    cursor.execute("""
        SELECT
            id_vendedor,
            nome,
            cpf,
            telefone,
            email

        FROM vendedores

        WHERE id_vendedor = %s
    """, (id_vendedor,))

    vendedor = cursor.fetchone()

    cursor.close()
    conexao.close()

    if not vendedor:
        return "Vendedor não encontrado.", 404

    return render_template(
        "editar_vendedor.html",
        vendedor=vendedor
    )


# ============================================================
# VENDEDORES - EXCLUSÃO
# ============================================================

@app.route(
    "/vendedores/<int:id_vendedor>/excluir",
    methods=["POST"]
)
def excluir_vendedor(id_vendedor):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        cursor.execute("""
            DELETE FROM vendedores
            WHERE id_vendedor = %s
        """, (id_vendedor,))

        conexao.commit()

    except Exception as erro:

        conexao.rollback()

        cursor.close()
        conexao.close()

        return f"""
        Não foi possível excluir o vendedor.
        <br><br>
        Ele pode possuir vendas vinculadas.
        <br><br>
        Erro: {erro}
        <br><br>
        <a href="/vendedores">Voltar</a>
        """

    cursor.close()
    conexao.close()

    return redirect(url_for("vendedores"))


# ============================================================
# VENDAS - LISTAGEM E PESQUISA
# ============================================================

@app.route("/vendas", methods=["GET"])
def vendas():

    busca = request.args.get("busca", "").strip()

    conexao = conectar()
    cursor = conexao.cursor()

    sql = """
        SELECT
            ve.id_venda,

            COALESCE(
                c.nome,
                c.razao_social
            ) AS cliente,

            vd.nome AS vendedor,

            ma.nome AS marca,
            mo.nome AS modelo,
            v.placa,

            ve.data_venda,
            ve.valor_venda,
            ve.forma_pagamento,
            ve.observacoes

        FROM vendas ve

        INNER JOIN clientes c
            ON ve.id_cliente = c.id_cliente

        INNER JOIN vendedores vd
            ON ve.id_vendedor = vd.id_vendedor

        INNER JOIN veiculos v
            ON ve.id_veiculo = v.id_veiculo

        INNER JOIN modelos mo
            ON v.id_modelo = mo.id_modelo

        INNER JOIN marcas ma
            ON mo.id_marca = ma.id_marca

        WHERE 1 = 1
    """

    parametros = []

    if busca:

        termo = f"%{busca}%"

        sql += """
            AND (
                COALESCE(c.nome, c.razao_social) ILIKE %s
                OR vd.nome ILIKE %s
                OR v.placa ILIKE %s
                OR ma.nome ILIKE %s
                OR mo.nome ILIKE %s
            )
        """

        parametros.extend([
            termo,
            termo,
            termo,
            termo,
            termo
        ])

    sql += """
        ORDER BY ve.data_venda DESC, ve.id_venda DESC
    """

    cursor.execute(sql, parametros)

    vendas = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template(
        "vendas.html",
        vendas=vendas,
        busca=busca
    )


# ============================================================
# VENDAS - NOVA VENDA
# ============================================================

@app.route("/vendas/nova", methods=["GET", "POST"])
def nova_venda():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id_cliente,

            COALESCE(
                nome,
                razao_social
            ) AS cliente,

            COALESCE(
                cpf,
                cnpj
            ) AS documento

        FROM clientes

        ORDER BY COALESCE(nome, razao_social)
    """)

    clientes_lista = cursor.fetchall()

    cursor.execute("""
        SELECT
            id_vendedor,
            nome

        FROM vendedores

        ORDER BY nome
    """)

    vendedores_lista = cursor.fetchall()

    cursor.execute("""
        SELECT
            v.id_veiculo,
            v.placa,
            ma.nome,
            mo.nome,
            v.ano_modelo,
            v.preco_venda

        FROM veiculos v

        INNER JOIN modelos mo
            ON v.id_modelo = mo.id_modelo

        INNER JOIN marcas ma
            ON mo.id_marca = ma.id_marca

        WHERE v.status = 'Disponível'

        ORDER BY ma.nome, mo.nome
    """)

    veiculos_lista = cursor.fetchall()

    if request.method == "POST":

        id_cliente = request.form["id_cliente"]
        id_vendedor = request.form["id_vendedor"]
        id_veiculo = request.form["id_veiculo"]
        data_venda = request.form["data_venda"]
        valor_venda = request.form["valor_venda"]

        forma_pagamento = request.form[
            "forma_pagamento"
        ]

        observacoes = vazio_para_none(
            request.form.get("observacoes")
        )

        try:

            cursor.execute("""
                SELECT status
                FROM veiculos
                WHERE id_veiculo = %s
                FOR UPDATE
            """, (id_veiculo,))

            resultado = cursor.fetchone()

            if not resultado:

                cursor.close()
                conexao.close()

                return """
                Veículo não encontrado.
                <br><br>
                <a href="/vendas/nova">Voltar</a>
                """

            if resultado[0] != "Disponível":

                conexao.rollback()

                cursor.close()
                conexao.close()

                return """
                Este veículo não está mais disponível.
                <br><br>
                <a href="/vendas/nova">Voltar</a>
                """

            cursor.execute("""
                INSERT INTO vendas (
                    id_cliente,
                    id_vendedor,
                    id_veiculo,
                    data_venda,
                    valor_venda,
                    forma_pagamento,
                    observacoes
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
            """, (
                id_cliente,
                id_vendedor,
                id_veiculo,
                data_venda,
                valor_venda,
                forma_pagamento,
                observacoes
            ))

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

            return f"""
            Não foi possível registrar a venda.
            <br><br>
            Erro: {erro}
            <br><br>
            <a href="/vendas/nova">Voltar</a>
            """

        cursor.close()
        conexao.close()

        return redirect(url_for("vendas"))

    cursor.close()
    conexao.close()

    return render_template(
        "nova_venda.html",
        clientes=clientes_lista,
        vendedores=vendedores_lista,
        veiculos=veiculos_lista
    )


# ============================================================
# VENDAS - EXCLUSÃO
# ============================================================

@app.route(
    "/vendas/<int:id_venda>/excluir",
    methods=["POST"]
)
def excluir_venda(id_venda):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        cursor.execute("""
            SELECT id_veiculo
            FROM vendas
            WHERE id_venda = %s
        """, (id_venda,))

        venda = cursor.fetchone()

        if not venda:

            cursor.close()
            conexao.close()

            return "Venda não encontrada.", 404

        id_veiculo = venda[0]

        cursor.execute("""
            DELETE FROM vendas
            WHERE id_venda = %s
        """, (id_venda,))

        cursor.execute("""
            UPDATE veiculos
            SET status = 'Disponível'
            WHERE id_veiculo = %s
        """, (id_veiculo,))

        conexao.commit()

    except Exception as erro:

        conexao.rollback()

        cursor.close()
        conexao.close()

        return f"""
        Não foi possível excluir a venda.
        <br><br>
        Erro: {erro}
        <br><br>
        <a href="/vendas">Voltar</a>
        """

    cursor.close()
    conexao.close()

    return redirect(url_for("vendas"))


# ============================================================
# MANUTENÇÕES - LISTAGEM E PESQUISA
# ============================================================

@app.route("/manutencoes", methods=["GET"])
def manutencoes():

    busca = request.args.get("busca", "").strip()

    conexao = conectar()
    cursor = conexao.cursor()

    sql = """
        SELECT
            m.id_manutencao,
            v.placa,
            ma.nome AS marca,
            mo.nome AS modelo,
            m.data_manutencao,
            m.tipo,
            m.descricao,
            m.quilometragem,
            m.valor

        FROM manutencoes m

        INNER JOIN veiculos v
            ON m.id_veiculo = v.id_veiculo

        INNER JOIN modelos mo
            ON v.id_modelo = mo.id_modelo

        INNER JOIN marcas ma
            ON mo.id_marca = ma.id_marca

        WHERE 1 = 1
    """

    parametros = []

    if busca:

        termo = f"%{busca}%"

        sql += """
            AND (
                v.placa ILIKE %s
                OR ma.nome ILIKE %s
                OR mo.nome ILIKE %s
                OR m.tipo ILIKE %s
                OR m.descricao ILIKE %s
            )
        """

        parametros.extend([
            termo,
            termo,
            termo,
            termo,
            termo
        ])

    sql += """
        ORDER BY
            m.data_manutencao DESC,
            m.id_manutencao DESC
    """

    cursor.execute(sql, parametros)

    manutencoes = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template(
        "manutencoes.html",
        manutencoes=manutencoes,
        busca=busca
    )


# ============================================================
# MANUTENÇÕES - NOVA
# ============================================================

@app.route(
    "/manutencoes/nova",
    methods=["GET", "POST"]
)
def nova_manutencao():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            v.id_veiculo,
            v.placa,
            ma.nome,
            mo.nome,
            v.quilometragem

        FROM veiculos v

        INNER JOIN modelos mo
            ON v.id_modelo = mo.id_modelo

        INNER JOIN marcas ma
            ON mo.id_marca = ma.id_marca

        ORDER BY ma.nome, mo.nome
    """)

    veiculos = cursor.fetchall()

    if request.method == "POST":

        id_veiculo = request.form["id_veiculo"]

        data_manutencao = request.form[
            "data_manutencao"
        ]

        tipo = request.form["tipo"]

        descricao = vazio_para_none(
            request.form.get("descricao")
        )

        quilometragem = vazio_para_none(
            request.form.get("quilometragem")
        )

        valor = vazio_para_none(
            request.form.get("valor")
        )

        try:

            cursor.execute("""
                INSERT INTO manutencoes (
                    id_veiculo,
                    data_manutencao,
                    tipo,
                    descricao,
                    valor,
                    quilometragem
                )
                VALUES (
                    %s, %s, %s,
                    %s, %s, %s
                )
            """, (
                id_veiculo,
                data_manutencao,
                tipo,
                descricao,
                valor,
                quilometragem
            ))

            if quilometragem is not None:

                cursor.execute("""
                    UPDATE veiculos
                    SET quilometragem = %s
                    WHERE id_veiculo = %s
                """, (
                    quilometragem,
                    id_veiculo
                ))

            conexao.commit()

        except Exception as erro:

            conexao.rollback()

            cursor.close()
            conexao.close()

            return f"""
            Não foi possível registrar a manutenção.
            <br><br>
            Erro: {erro}
            <br><br>
            <a href="/manutencoes/nova">Voltar</a>
            """

        cursor.close()
        conexao.close()

        return redirect(
            url_for("manutencoes")
        )

    cursor.close()
    conexao.close()

    return render_template(
        "nova_manutencao.html",
        veiculos=veiculos
    )


# ============================================================
# MANUTENÇÕES - EDIÇÃO
# ============================================================

@app.route(
    "/manutencoes/<int:id_manutencao>/editar",
    methods=["GET", "POST"]
)
def editar_manutencao(id_manutencao):

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            v.id_veiculo,
            v.placa,
            ma.nome,
            mo.nome

        FROM veiculos v

        INNER JOIN modelos mo
            ON v.id_modelo = mo.id_modelo

        INNER JOIN marcas ma
            ON mo.id_marca = ma.id_marca

        ORDER BY ma.nome, mo.nome
    """)

    veiculos = cursor.fetchall()

    if request.method == "POST":

        id_veiculo = request.form[
            "id_veiculo"
        ]

        data_manutencao = request.form[
            "data_manutencao"
        ]

        tipo = request.form["tipo"]

        descricao = vazio_para_none(
            request.form.get("descricao")
        )

        quilometragem = vazio_para_none(
            request.form.get("quilometragem")
        )

        valor = vazio_para_none(
            request.form.get("valor")
        )

        try:

            cursor.execute("""
                UPDATE manutencoes

                SET
                    id_veiculo = %s,
                    data_manutencao = %s,
                    tipo = %s,
                    descricao = %s,
                    valor = %s,
                    quilometragem = %s

                WHERE id_manutencao = %s
            """, (
                id_veiculo,
                data_manutencao,
                tipo,
                descricao,
                valor,
                quilometragem,
                id_manutencao
            ))

            if quilometragem is not None:

                cursor.execute("""
                    UPDATE veiculos
                    SET quilometragem = %s
                    WHERE id_veiculo = %s
                """, (
                    quilometragem,
                    id_veiculo
                ))

            conexao.commit()

        except Exception as erro:

            conexao.rollback()

            cursor.close()
            conexao.close()

            return f"""
            Não foi possível atualizar a manutenção.
            <br><br>
            Erro: {erro}
            <br><br>
            <a href="/manutencoes/{id_manutencao}/editar">
                Voltar
            </a>
            """

        cursor.close()
        conexao.close()

        return redirect(
            url_for("manutencoes")
        )

    cursor.execute("""
        SELECT
            id_manutencao,
            id_veiculo,
            data_manutencao,
            tipo,
            descricao,
            valor,
            quilometragem

        FROM manutencoes

        WHERE id_manutencao = %s
    """, (id_manutencao,))

    manutencao = cursor.fetchone()

    cursor.close()
    conexao.close()

    if not manutencao:
        return "Manutenção não encontrada.", 404

    return render_template(
        "editar_manutencao.html",
        manutencao=manutencao,
        veiculos=veiculos
    )


# ============================================================
# MANUTENÇÕES - EXCLUSÃO
# ============================================================

@app.route(
    "/manutencoes/<int:id_manutencao>/excluir",
    methods=["POST"]
)
def excluir_manutencao(id_manutencao):

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        cursor.execute("""
            DELETE FROM manutencoes
            WHERE id_manutencao = %s
        """, (id_manutencao,))

        conexao.commit()

    except Exception as erro:

        conexao.rollback()

        cursor.close()
        conexao.close()

        return f"""
        Não foi possível excluir a manutenção.
        <br><br>
        Erro: {erro}
        <br><br>
        <a href="/manutencoes">Voltar</a>
        """

    cursor.close()
    conexao.close()

    return redirect(
        url_for("manutencoes")
    )

# ============================================================
# RELATÓRIOS / DASHBOARD
# ============================================================

from relatorios import criar_relatorios_blueprint

relatorios_bp = criar_relatorios_blueprint(conectar)

app.register_blueprint(relatorios_bp)


# ============================================================
# PROPOSTAS / PEDIDOS / ACOMPANHAMENTO DE COMPRA
# ============================================================
from decimal import Decimal, InvalidOperation

STATUS_ATIVOS_COMPRA = ("Pendente", "Em atendimento", "Em análise", "Informações solicitadas", "Aprovada")
STATUS_COMPRA = ("Pendente", "Em atendimento", "Em análise", "Informações solicitadas", "Aprovada", "Recusada", "Cancelada", "Concluída")
FORMAS_COMPRA = ("À vista", "Financiamento", "Consórcio", "A combinar")


def token_compra():
    token = session.get("csrf_compra")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_compra"] = token
    return token


def verificar_token_compra():
    esperado = session.get("csrf_compra")
    recebido = request.form.get("csrf_token", "")
    if not esperado or not secrets.compare_digest(esperado, recebido):
        abort(400, description="Formulário inválido. Reabra a página.")


def numero_protocolo(id_solicitacao):
    return f"TOT-{int(id_solicitacao):08d}"


@app.context_processor
def helpers_compra():
    return {"numero_protocolo": numero_protocolo}


def decimal_formulario(valor, *, obrigatorio=False):
    texto = (valor or "").strip().replace("R$", "").replace(" ", "")
    if not texto:
        if obrigatorio:
            raise ValueError("Informe o valor da proposta.")
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise ValueError("Informe um valor numérico válido.")
    if not numero.is_finite() or numero <= 0 or numero > Decimal("999999999999.99"):
        raise ValueError("Informe um valor positivo válido.")
    if numero.as_tuple().exponent < -2:
        raise ValueError("Utilize no máximo duas casas decimais.")
    return numero


@app.route("/comprar/<int:id_veiculo>", methods=["GET", "POST"])
def comprar_veiculo(id_veiculo):
    if session.get("usuario_perfil") != "Cliente" or not session.get("id_cliente"):
        abort(403)
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT v.id_veiculo, ma.nome, mo.nome, v.ano_modelo,
                       v.cor, v.preco_venda, v.status, v.imagem
                FROM veiculos v
                JOIN modelos mo ON mo.id_modelo=v.id_modelo
                JOIN marcas ma ON ma.id_marca=mo.id_marca
                WHERE v.id_veiculo=%s
            """, (id_veiculo,))
            veiculo = cursor.fetchone()
            if not veiculo:
                abort(404)
            if veiculo[6] != "Disponível" or veiculo[5] is None:
                abort(409, description="Veículo indisponível para novas propostas.")
            erro = None
            if request.method == "POST":
                verificar_token_compra()
                forma = request.form.get("forma_pagamento", "")
                obs = request.form.get("observacoes", "").strip()[:1500]
                try:
                    if forma not in FORMAS_COMPRA:
                        raise ValueError("Selecione a forma de pagamento.")
                    valor = decimal_formulario(request.form.get("valor_proposta"), obrigatorio=True)
                    entrada = decimal_formulario(request.form.get("entrada_proposta"))
                    parcelas_texto = request.form.get("parcelas_proposta", "").strip()
                    parcelas = int(parcelas_texto) if parcelas_texto else None
                    if parcelas is not None and not (1 <= parcelas <= 120):
                        raise ValueError("A quantidade de parcelas deve ficar entre 1 e 120.")
                    if entrada is not None and entrada > valor:
                        raise ValueError("A entrada não pode ultrapassar a proposta.")
                    # Sem valores de entrada/parcelamento para pagamentos sem parcelamento.
                    if forma == "À vista" and (entrada is not None or parcelas is not None):
                        raise ValueError("Para pagamento à vista, deixe entrada e parcelas vazios.")
                except (ValueError, TypeError) as e:
                    erro = str(e)
                if erro is None:
                    cursor.execute("SELECT status, preco_venda FROM veiculos WHERE id_veiculo=%s FOR UPDATE", (id_veiculo,))
                    atual = cursor.fetchone()
                    if not atual or atual[0] != "Disponível":
                        conexao.rollback()
                        abort(409, description="Este veículo não está mais disponível.")
                    cursor.execute("""
                        SELECT id_solicitacao FROM solicitacoes_compra
                        WHERE id_usuario=%s AND id_veiculo=%s
                          AND status IN ('Pendente','Em atendimento','Em análise','Informações solicitadas','Aprovada')
                        LIMIT 1
                    """, (session["usuario_id"], id_veiculo))
                    repetido = cursor.fetchone()
                    if repetido:
                        conexao.rollback()
                        return redirect(url_for("detalhe_minha_compra", id_solicitacao=repetido[0]))
                    cursor.execute("""
                        INSERT INTO solicitacoes_compra
                        (id_usuario,id_cliente,id_veiculo,forma_pagamento,observacoes,
                         preco_solicitado,valor_proposta,entrada_proposta,parcelas_proposta)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id_solicitacao
                    """, (session["usuario_id"],session["id_cliente"],id_veiculo,forma,
                           obs or None,atual[1],valor,entrada,parcelas))
                    numero = cursor.fetchone()[0]
                    conexao.commit()
                    return redirect(url_for("detalhe_minha_compra", id_solicitacao=numero))
            return render_template("comprar.html", veiculo=veiculo, erro=erro, csrf_token=token_compra())
    finally:
        conexao.close()


def buscar_proposta(cursor, id_solicitacao, *, bloquear=False):
    cursor.execute("""
        SELECT s.id_solicitacao, s.id_usuario, s.id_cliente, s.id_veiculo,
               s.criado_em, s.forma_pagamento, s.observacoes, s.preco_solicitado,
               s.status, s.valor_proposta, s.entrada_proposta, s.parcelas_proposta,
               s.resposta_administracao, s.id_venda, s.atualizado_em,
               u.nome, u.email, ma.nome, mo.nome, v.ano_modelo, v.placa, v.status
        FROM solicitacoes_compra s
        JOIN usuarios u ON u.id_usuario=s.id_usuario
        JOIN veiculos v ON v.id_veiculo=s.id_veiculo
        JOIN modelos mo ON mo.id_modelo=v.id_modelo
        JOIN marcas ma ON ma.id_marca=mo.id_marca
        WHERE s.id_solicitacao=%s
    """ + (" FOR UPDATE OF s" if bloquear else ""), (id_solicitacao,))
    return cursor.fetchone()


@app.route("/minhas-compras")
def minhas_compras():
    if session.get("usuario_perfil") != "Cliente":
        abort(403)
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT s.id_solicitacao, s.criado_em, ma.nome, mo.nome, v.ano_modelo,
                       s.valor_proposta, s.status, s.atualizado_em
                FROM solicitacoes_compra s JOIN veiculos v ON v.id_veiculo=s.id_veiculo
                JOIN modelos mo ON mo.id_modelo=v.id_modelo
                JOIN marcas ma ON ma.id_marca=mo.id_marca
                WHERE s.id_usuario=%s ORDER BY s.criado_em DESC
            """, (session["usuario_id"],))
            pedidos = cursor.fetchall()
        return render_template("minhas_compras.html", pedidos=pedidos)
    finally:
        conexao.close()


@app.route("/minhas-compras/<int:id_solicitacao>")
def detalhe_minha_compra(id_solicitacao):
    if session.get("usuario_perfil") != "Cliente":
        abort(403)
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            pedido = buscar_proposta(cursor, id_solicitacao)
        if not pedido or pedido[1] != session.get("usuario_id"):
            abort(404)
        return render_template("detalhe_compra.html", pedido=pedido, csrf_token=token_compra())
    finally:
        conexao.close()


@app.route("/minhas-compras/<int:id_solicitacao>/cancelar", methods=["POST"])
def cancelar_minha_compra(id_solicitacao):
    if session.get("usuario_perfil") != "Cliente":
        abort(403)
    verificar_token_compra()
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE solicitacoes_compra SET status='Cancelada', atualizado_em=NOW()
                WHERE id_solicitacao=%s AND id_usuario=%s
                  AND status IN ('Pendente','Em atendimento','Em análise','Informações solicitadas')
                RETURNING id_solicitacao
            """, (id_solicitacao, session["usuario_id"]))
            if not cursor.fetchone():
                conexao.rollback()
                abort(409, description="Pedido inexistente ou já não pode ser cancelado.")
        conexao.commit()
    finally:
        conexao.close()
    return redirect(url_for("detalhe_minha_compra", id_solicitacao=id_solicitacao))


@app.route("/solicitacoes-compra")
def listar_solicitacoes_compra():
    if session.get("usuario_perfil") not in {"Superuser","Administrador","Vendedor"}:
        abort(403)
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT s.id_solicitacao, s.criado_em, u.nome, ma.nome, mo.nome,
                       s.valor_proposta, s.status, s.atualizado_em
                FROM solicitacoes_compra s
                JOIN usuarios u ON u.id_usuario=s.id_usuario
                JOIN veiculos v ON v.id_veiculo=s.id_veiculo
                JOIN modelos mo ON mo.id_modelo=v.id_modelo
                JOIN marcas ma ON ma.id_marca=mo.id_marca
                ORDER BY s.criado_em DESC, s.id_solicitacao DESC
            """)
            pedidos = cursor.fetchall()
        return render_template("solicitacoes_compra.html", pedidos=pedidos)
    finally:
        conexao.close()


@app.route("/solicitacoes-compra/<int:id_solicitacao>")
def detalhe_solicitacao_compra(id_solicitacao):
    if session.get("usuario_perfil") not in {"Superuser","Administrador","Vendedor"}:
        abort(403)
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            pedido = buscar_proposta(cursor, id_solicitacao)
            if not pedido:
                abort(404)
            cursor.execute("SELECT id_vendedor, nome FROM vendedores ORDER BY nome")
            vendedores = cursor.fetchall()
        return render_template("avaliar_compra.html", pedido=pedido, vendedores=vendedores,
                               csrf_token=token_compra())
    finally:
        conexao.close()


@app.route("/solicitacoes-compra/<int:id_solicitacao>/status", methods=["POST"])
def atualizar_solicitacao_compra(id_solicitacao):
    if session.get("usuario_perfil") not in {"Superuser", "Administrador"}:
        abort(403)
    verificar_token_compra()
    novo = request.form.get("status", "")
    if novo not in {"Em análise", "Informações solicitadas", "Aprovada", "Recusada", "Cancelada"}:
        abort(400)
    resposta = request.form.get("resposta_administracao", "").strip()[:1500]
    if novo in {"Informações solicitadas", "Recusada"} and not resposta:
        abort(400, description="Informe uma justificativa ou mensagem ao cliente.")
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            atual = buscar_proposta(cursor, id_solicitacao, bloquear=True)
            if not atual or atual[8] in {"Recusada", "Cancelada", "Concluída"}:
                conexao.rollback()
                abort(409, description="Pedido encerrado ou inexistente.")
            if atual[8] == "Aprovada" and novo != "Cancelada":
                conexao.rollback()
                abort(409, description="Proposta já aprovada. Conclua a venda ou cancele.")
            if novo == "Aprovada":
                # Verifica se o veículo foi vendido antes de aprovar.
                cursor.execute("SELECT status FROM veiculos WHERE id_veiculo=%s FOR UPDATE", (atual[3],))
                if cursor.fetchone()[0] != "Disponível":
                    conexao.rollback()
                    abort(409, description="Veículo já não está disponível.")
                cursor.execute("""
                    SELECT id_solicitacao FROM solicitacoes_compra
                    WHERE id_veiculo=%s AND id_solicitacao<>%s AND status='Aprovada'
                    LIMIT 1
                """, (atual[3],id_solicitacao))
                if cursor.fetchone():
                    conexao.rollback()
                    abort(409, description="Já existe proposta aprovada para esse veículo.")
            cursor.execute("""
                UPDATE solicitacoes_compra SET status=%s, resposta_administracao=%s,
                    atualizado_em=NOW(), avaliado_em=NOW()
                WHERE id_solicitacao=%s
            """, (novo, resposta or None, id_solicitacao))
        conexao.commit()
    finally:
        conexao.close()
    return redirect(url_for("detalhe_solicitacao_compra", id_solicitacao=id_solicitacao))


@app.route("/solicitacoes-compra/<int:id_solicitacao>/concluir", methods=["POST"])
def concluir_compra(id_solicitacao):
    if session.get("usuario_perfil") not in {"Superuser", "Administrador"}:
        abort(403)
    verificar_token_compra()
    try:
        id_vendedor = int(request.form.get("id_vendedor", ""))
        valor = decimal_formulario(request.form.get("valor_final"), obrigatorio=True)
        forma = request.form.get("forma_pagamento", "")
        if forma not in FORMAS_COMPRA:
            raise ValueError("Forma de pagamento inválida.")
        if id_vendedor <= 0:
            raise ValueError("Selecione um vendedor válido.")
    except (ValueError,TypeError) as e:
        abort(400, description=str(e))
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            # Bloqueio do pedido + bloqueio do veículo asseguram atomicidade.
            pedido = buscar_proposta(cursor, id_solicitacao, bloquear=True)
            if not pedido or pedido[8] != "Aprovada" or pedido[13] is not None:
                conexao.rollback()
                abort(409, description="A proposta precisa estar aprovada e não concluída.")
            cursor.execute("SELECT status FROM veiculos WHERE id_veiculo=%s FOR UPDATE", (pedido[3],))
            veiculo = cursor.fetchone()
            if not veiculo or veiculo[0] != "Disponível":
                conexao.rollback()
                abort(409, description="Veículo indisponível. Nenhuma venda foi registrada.")
            cursor.execute("SELECT 1 FROM vendedores WHERE id_vendedor=%s", (id_vendedor,))
            if not cursor.fetchone():
                conexao.rollback()
                abort(400, description="Vendedor não encontrado.")
            cursor.execute("""
                INSERT INTO vendas (id_cliente,id_vendedor,id_veiculo,data_venda,
                                    valor_venda,forma_pagamento,observacoes)
                VALUES (%s,%s,%s,CURRENT_DATE,%s,%s,%s) RETURNING id_venda
            """, (pedido[2], id_vendedor, pedido[3], valor, forma,
                   f"Venda do protocolo {numero_protocolo(id_solicitacao)}"))
            id_venda = cursor.fetchone()[0]
            cursor.execute("UPDATE veiculos SET status='Vendido' WHERE id_veiculo=%s", (pedido[3],))
            cursor.execute("""
                UPDATE solicitacoes_compra SET status='Concluída', id_venda=%s,
                    finalizado_em=NOW(), atualizado_em=NOW()
                WHERE id_solicitacao=%s
            """, (id_venda,id_solicitacao))
            cursor.execute("""
                UPDATE solicitacoes_compra SET status='Recusada', atualizado_em=NOW(),
                    resposta_administracao='Veículo vendido em outra proposta.'
                WHERE id_veiculo=%s AND id_solicitacao<>%s
                AND status IN ('Pendente','Em atendimento','Em análise',
                               'Informações solicitadas','Aprovada')
            """, (pedido[3],id_solicitacao))
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    return redirect(url_for("detalhe_solicitacao_compra", id_solicitacao=id_solicitacao))


# ============================================================
# AUTENTICAÇÃO, USUÁRIOS E CONTROLE DE ACESSO
# ============================================================

from auth import criar_auth_blueprint
from usuarios import criar_usuarios_blueprint

app.register_blueprint(criar_auth_blueprint(conectar))
app.register_blueprint(criar_usuarios_blueprint(conectar))


@app.before_request
def verificar_acesso():
    """Protege as rotas existentes (inclusive chamadas por URL direta)."""
    endpoint = request.endpoint or ""

    # Arquivos estáticos e páginas de entrada pública.
    if endpoint in {"static", "auth.login", "auth.cadastro"}:
        return None

    if not session.get("usuario_id"):
        if endpoint == "auth.logout":
            return redirect(url_for("auth.login"))
        return redirect(url_for("auth.login", next=request.path))

    perfil = session.get("usuario_perfil")
    if perfil not in {"Superuser", "Administrador", "Vendedor", "Cliente"}:
        session.clear()
        return redirect(url_for("auth.login"))

    if endpoint == "auth.logout":
        return None

    # Somente o Superuser pode consultar, criar, editar e excluir usuários.
    if endpoint.startswith("usuarios."):
        if perfil != "Superuser":
            abort(403)
        return None

    # O Cliente só acessa o catálogo e os detalhes dos veículos.
    if perfil == "Cliente":
        if endpoint not in {"index", "visualizar_veiculo", "comprar_veiculo", "minhas_compras", "detalhe_minha_compra", "cancelar_minha_compra"}:
            abort(403)
        return None

    # O Vendedor pode operar cadastros e vendas, mas não excluir registros.
    if perfil == "Vendedor":
        if endpoint.startswith("excluir_") or endpoint in {"excluir_venda"}:
            abort(403)
        return None

    # Administradores não podem excluir clientes.
    if perfil == "Administrador" and endpoint == "excluir_cliente":
        abort(403)

    return None


# ============================================================
# INICIAR SISTEMA
# ============================================================

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")