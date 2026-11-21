import pytest
from app import create_app


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test-estoque.db"
    test_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE": str(db_path),
    })
    with test_app.test_client() as client:
        yield client


def add_supplier(client, name="Fornecedor Exemplo"):
    response = client.post("/suppliers/new", data={"name": name, "email": "contato@example.com"}, follow_redirects=True)
    assert response.status_code == 200
    return response


def add_product(client, sku="MAT-001", name="Parafuso M8", supplier_id=""):
    response = client.post("/products/new", data={
        "sku": sku,
        "name": name,
        "category": "Fixadores",
        "unit": "un",
        "min_stock": "2",
        "supplier_id": supplier_id,
        "description": "Produto para testes",
    }, follow_redirects=True)
    assert response.status_code == 200
    return response


def add_movement(client, product_id, movement_type, quantity, note="teste"):
    return client.post("/movements/new", data={
        "product_id": str(product_id),
        "movement_type": movement_type,
        "quantity": str(quantity),
        "note": note,
    }, follow_redirects=True)


def test_dashboard_and_empty_pages_load(client):
    for path in ("/", "/products", "/suppliers", "/movements"):
        response = client.get(path)
        assert response.status_code == 200


def test_product_and_supplier_crud(client):
    add_supplier(client)
    add_product(client, supplier_id="1")
    response = client.get("/products")
    assert b"Parafuso M8" in response.data
    assert b"Fornecedor Exemplo" in response.data

    response = client.post("/products/1/edit", data={
        "sku": "MAT-001", "name": "Parafuso M10", "category": "Fixadores",
        "unit": "un", "min_stock": "3", "supplier_id": "1", "description": "Atualizado",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Parafuso M10" in response.data

    response = client.post("/suppliers/1/edit", data={"name": "Fornecedor Atualizado", "email": "novo@example.com"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Fornecedor Atualizado" in response.data

    # Não permite excluir fornecedor referenciado por produto.
    response = client.post("/suppliers/1/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"associado a produtos" in response.data


def test_entry_exit_and_stock_balance(client):
    add_product(client)
    assert add_movement(client, 1, "ENTRADA", 10).status_code == 200
    assert add_movement(client, 1, "SAIDA", 3).status_code == 200
    response = client.get("/products")
    assert b"7 un" in response.data
    response = client.get("/movements?type=SAIDA")
    assert response.status_code == 200
    assert b"Saida" in response.data or b"Sa\xc3\xadda" in response.data


def test_exit_cannot_exceed_available_stock(client):
    add_product(client)
    add_movement(client, 1, "ENTRADA", 4)
    response = add_movement(client, 1, "SAIDA", 5)
    assert response.status_code == 200
    assert b"Estoque insuficiente" in response.data
    # Saldo continua sendo quatro unidades.
    products = client.get("/products")
    assert b"4 un" in products.data


def test_invalid_zero_quantity_is_rejected(client):
    add_product(client)
    response = add_movement(client, 1, "ENTRADA", 0)
    assert response.status_code == 200
    assert b"maior que zero" in response.data
    assert b"0 un" in client.get("/products").data


def test_delete_product_without_movements(client):
    add_product(client)
    response = client.post("/products/1/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Parafuso M8" not in response.data


def test_product_with_movements_cannot_be_deleted(client):
    add_product(client)
    add_movement(client, 1, "ENTRADA", 10)
    response = client.post("/products/1/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"possui movimenta\xc3\xa7\xc3\xb5es" in response.data
