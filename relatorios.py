from flask import Blueprint, render_template


def criar_relatorios_blueprint(conectar):

    relatorios_bp = Blueprint(
        "relatorios",
        __name__
    )

    @relatorios_bp.route("/relatorios")
    def pagina_relatorios():

        conexao = conectar()
        cursor = conexao.cursor()

        # Total de veículos
        cursor.execute("""
            SELECT COUNT(*)
            FROM veiculos
        """)
        total_veiculos = cursor.fetchone()[0]

        # Veículos disponíveis
        cursor.execute("""
            SELECT COUNT(*)
            FROM veiculos
            WHERE status = 'Disponível'
        """)
        veiculos_disponiveis = cursor.fetchone()[0]

        # Veículos vendidos
        cursor.execute("""
            SELECT COUNT(*)
            FROM veiculos
            WHERE status = 'Vendido'
        """)
        veiculos_vendidos = cursor.fetchone()[0]

        # Valor atual do estoque
        cursor.execute("""
            SELECT COALESCE(SUM(preco_venda), 0)
            FROM veiculos
            WHERE status = 'Disponível'
        """)
        valor_estoque = cursor.fetchone()[0]

        # Faturamento total
        cursor.execute("""
            SELECT COALESCE(SUM(valor_venda), 0)
            FROM vendas
        """)
        faturamento = cursor.fetchone()[0]

        # Total de clientes
        cursor.execute("""
            SELECT COUNT(*)
            FROM clientes
        """)
        total_clientes = cursor.fetchone()[0]

        # Total de vendedores
        cursor.execute("""
            SELECT COUNT(*)
            FROM vendedores
        """)
        total_vendedores = cursor.fetchone()[0]

        # Custo total das manutenções
        cursor.execute("""
            SELECT COALESCE(SUM(valor), 0)
            FROM manutencoes
        """)
        total_manutencoes = cursor.fetchone()[0]

        # Desempenho por vendedor
        cursor.execute("""
            SELECT
                vd.nome,
                COUNT(ve.id_venda) AS quantidade,
                COALESCE(SUM(ve.valor_venda), 0) AS faturamento

            FROM vendedores vd

            LEFT JOIN vendas ve
                ON vd.id_vendedor = ve.id_vendedor

            GROUP BY
                vd.id_vendedor,
                vd.nome

            ORDER BY
                quantidade DESC,
                faturamento DESC,
                vd.nome

            LIMIT 10
        """)

        vendas_vendedor = cursor.fetchall()

        # Vendas por marca
        cursor.execute("""
            SELECT
                ma.nome,
                COUNT(ve.id_venda) AS quantidade

            FROM vendas ve

            INNER JOIN veiculos v
                ON ve.id_veiculo = v.id_veiculo

            INNER JOIN modelos mo
                ON v.id_modelo = mo.id_modelo

            INNER JOIN marcas ma
                ON mo.id_marca = ma.id_marca

            GROUP BY ma.nome

            ORDER BY
                quantidade DESC,
                ma.nome
        """)

        vendas_marca = cursor.fetchall()

        # Últimas vendas
        cursor.execute("""
            SELECT
                ve.data_venda,

                COALESCE(
                    c.nome,
                    c.razao_social
                ) AS cliente,

                ma.nome,
                mo.nome,
                v.placa,
                vd.nome,
                ve.valor_venda

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

            ORDER BY
                ve.data_venda DESC,
                ve.id_venda DESC

            LIMIT 5
        """)

        ultimas_vendas = cursor.fetchall()

        cursor.close()
        conexao.close()

        return render_template(
            "relatorios.html",

            total_veiculos=total_veiculos,
            veiculos_disponiveis=veiculos_disponiveis,
            veiculos_vendidos=veiculos_vendidos,

            valor_estoque=valor_estoque,
            faturamento=faturamento,

            total_clientes=total_clientes,
            total_vendedores=total_vendedores,
            total_manutencoes=total_manutencoes,

            vendas_vendedor=vendas_vendedor,
            vendas_marca=vendas_marca,
            ultimas_vendas=ultimas_vendas
        )

    return relatorios_bp