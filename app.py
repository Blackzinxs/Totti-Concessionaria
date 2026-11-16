from flask import Flask, render_template, request, redirect, url_for, session, abort
from werkzeug.utils import secure_filename
import psycopg2
import os
import uuid
import secrets


app = Flask(__name__)
# Configure uma SECRET_KEY fixa e secreta em Render > Environment.
# O valor aleatório abaixo serve somente como fallback de desenvolvimento.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("RENDER"):
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

os.makedirs(
    PASTA_IMAGENS_VEICULOS,
    exist_ok=True
)

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
# SOLICITAÇÕES DE COMPRA (NÃO SÃO VENDAS CONCLUÍDAS)
# ============================================================

def token_compra():
    token = session.get("csrf_compra")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_compra"] = token
    return token


def verificar_token_compra():
    if not secrets.compare_digest(
        str(session.get("csrf_compra", "")),
        str(request.form.get("csrf_token", ""))
    ) or not session.get("csrf_compra"):
        abort(400, description="Formulário expirado. Reabra a página e tente novamente.")


@app.route("/comprar/<int:id_veiculo>", methods=["GET", "POST"])
def comprar_veiculo(id_veiculo):
    if session.get("usuario_perfil") != "Cliente":
        abort(403)
    usuario_id = session.get("usuario_id")
    id_cliente = session.get("id_cliente")
    if not id_cliente:
        abort(403, description="Seu cadastro não possui um cliente associado.")

    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT v.id_veiculo, ma.nome, mo.nome, v.ano_modelo,
                       v.cor, v.preco_venda, v.status, v.imagem
                FROM veiculos v
                JOIN modelos mo ON mo.id_modelo = v.id_modelo
                JOIN marcas ma ON ma.id_marca = mo.id_marca
                WHERE v.id_veiculo = %s
            """, (id_veiculo,))
            veiculo = cursor.fetchone()
            if not veiculo:
                abort(404)
            if veiculo[6] != "Disponível" or veiculo[5] is None:
                abort(409, description="Este veículo não está disponível para compra.")

            erro = None
            if request.method == "POST":
                verificar_token_compra()
                forma = request.form.get("forma_pagamento", "")
                observacoes = request.form.get("observacoes", "").strip()[:1000]
                if forma not in {"À vista", "Financiamento", "Consórcio", "A combinar"}:
                    erro = "Selecione uma forma de pagamento válida."
                else:
                    # Bloqueia o veículo para verificar disponibilidade e pedido duplicado.
                    cursor.execute("SELECT status FROM veiculos WHERE id_veiculo=%s FOR UPDATE", (id_veiculo,))
                    atual = cursor.fetchone()
                    if not atual or atual[0] != "Disponível":
                        conexao.rollback()
                        abort(409, description="Este veículo não está mais disponível.")
                    cursor.execute("""
                        SELECT id_solicitacao FROM solicitacoes_compra
                        WHERE id_usuario=%s AND id_veiculo=%s AND status IN ('Pendente','Em atendimento')
                        LIMIT 1
                    """, (usuario_id, id_veiculo))
                    if cursor.fetchone():
                        erro = "Você já tem uma solicitação em aberto para este veículo."
                    else:
                        cursor.execute("""
                            INSERT INTO solicitacoes_compra
                            (id_usuario, id_cliente, id_veiculo, forma_pagamento, observacoes, preco_solicitado)
                            VALUES (%s,%s,%s,%s,%s,%s)
                        """, (usuario_id, id_cliente, id_veiculo, forma, observacoes or None, veiculo[5]))
                        conexao.commit()
                        return render_template("compra_sucesso.html", veiculo=veiculo)
            return render_template("comprar.html", veiculo=veiculo, erro=erro,
                                   csrf_token=token_compra())
    finally:
        conexao.close()


@app.route("/solicitacoes-compra", methods=["GET"])
def listar_solicitacoes_compra():
    if session.get("usuario_perfil") not in {"Superuser", "Administrador", "Vendedor"}:
        abort(403)
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT s.id_solicitacao, s.criado_em, u.nome, u.email,
                       ma.nome, mo.nome, v.ano_modelo, v.placa,
                       s.preco_solicitado, s.forma_pagamento, s.observacoes,
                       s.status, s.id_veiculo
                FROM solicitacoes_compra s
                JOIN usuarios u ON u.id_usuario=s.id_usuario
                JOIN veiculos v ON v.id_veiculo=s.id_veiculo
                JOIN modelos mo ON mo.id_modelo=v.id_modelo
                JOIN marcas ma ON ma.id_marca=mo.id_marca
                ORDER BY s.criado_em DESC, s.id_solicitacao DESC
            """)
            solicitacoes = cursor.fetchall()
        return render_template("solicitacoes_compra.html", solicitacoes=solicitacoes,
                               csrf_token=token_compra())
    finally:
        conexao.close()


@app.route("/solicitacoes-compra/<int:id_solicitacao>/status", methods=["POST"])
def atualizar_solicitacao_compra(id_solicitacao):
    if session.get("usuario_perfil") not in {"Superuser", "Administrador"}:
        abort(403)
    verificar_token_compra()
    novo_status = request.form.get("status", "")
    if novo_status not in {"Em atendimento", "Cancelada"}:
        abort(400)
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE solicitacoes_compra SET status=%s, atualizado_em=NOW()
                WHERE id_solicitacao=%s AND status='Pendente'
                RETURNING id_solicitacao
            """, (novo_status, id_solicitacao))
            if cursor.fetchone() is None:
                conexao.rollback()
                abort(409, description="Solicitação já atualizada ou não encontrada.")
        conexao.commit()
    finally:
        conexao.close()
    return redirect(url_for("listar_solicitacoes_compra"))


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
        if endpoint not in {"index", "visualizar_veiculo", "comprar_veiculo"}:
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