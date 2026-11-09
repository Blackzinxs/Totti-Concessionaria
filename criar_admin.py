from getpass import getpass

from werkzeug.security import generate_password_hash

from app import conectar


print()
print("==========================================")
print("   TOTTI CONCESSIONARIA")
print("   CRIAÇÃO DO ADMINISTRADOR")
print("==========================================")
print()


nome = input(
    "Nome do administrador: "
).strip()


email = input(
    "E-mail: "
).strip().lower()


senha = getpass(
    "Senha: "
)


confirmar_senha = getpass(
    "Confirme a senha: "
)


if not nome:

    print(
        "O nome não pode ficar vazio."
    )

    raise SystemExit


if not email:

    print(
        "O e-mail não pode ficar vazio."
    )

    raise SystemExit


if not senha:

    print(
        "A senha não pode ficar vazia."
    )

    raise SystemExit


if senha != confirmar_senha:

    print()
    print(
        "As senhas não são iguais."
    )

    raise SystemExit


senha_hash = generate_password_hash(
    senha
)


conexao = conectar()
cursor = conexao.cursor()


cursor.execute("""
    SELECT id_usuario
    FROM usuarios
    WHERE LOWER(email) = LOWER(%s)
""", (email,))


usuario_existente = cursor.fetchone()


if usuario_existente:

    print()
    print(
        "Já existe um usuário "
        "cadastrado com esse e-mail."
    )

    cursor.close()
    conexao.close()

    raise SystemExit


cursor.execute("""
    INSERT INTO usuarios (
        nome,
        email,
        senha,
        perfil,
        ativo
    )
    VALUES (
        %s,
        %s,
        %s,
        %s,
        TRUE
    )
""", (
    nome,
    email,
    senha_hash,
    "Administrador"
))


conexao.commit()

cursor.close()
conexao.close()


print()
print(
    "Administrador criado com sucesso!"
)
print()