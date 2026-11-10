import pytest
from app import app as flask_app, init_db


@pytest.fixture()
def client(tmp_path):
    database = tmp_path / "test.db"
    flask_app.config.update(TESTING=True, DATABASE=str(database))
    init_db()
    with flask_app.test_client() as test_client:
        yield test_client


def add_client(client, name="Ana Souza"):
    return client.post("/clientes", data={"name": name, "phone": "(41) 99999-9999"}, follow_redirects=True)


def add_order(client, **overrides):
    add_client(client)
    data = {
        "client_id": "1",
        "description": "20 caixas personalizadas",
        "order_date": "2026-10-01",
        "deadline": "2026-10-15",
        "value": "180.00",
        "status": "Pendente",
        "notes": "Personalização azul e branco",
    }
    data.update(overrides)
    return client.post("/pedidos/novo", data=data, follow_redirects=True)


def test_dashboard_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Vamos organizar seus pedidos" in response.data


def test_client_can_be_created(client):
    response = add_client(client)
    assert response.status_code == 200
    assert "Ana Souza" in response.get_data(as_text=True)


def test_client_requires_name_and_phone(client):
    response = client.post("/clientes", data={"name": "", "phone": ""}, follow_redirects=True)
    assert "Informe o nome e o telefone" in response.get_data(as_text=True)


def test_order_can_be_created_and_listed(client):
    response = add_order(client)
    assert response.status_code == 200
    assert "20 caixas personalizadas" in response.get_data(as_text=True)
    assert "R$ 180,00" in response.get_data(as_text=True)


def test_order_requires_client(client):
    response = client.post("/pedidos/novo", data={
        "client_id": "", "description": "Caixas", "order_date": "2026-10-01",
        "deadline": "2026-10-15", "value": "10", "status": "Pendente"
    })
    assert response.status_code == 400


def test_deadline_cannot_precede_order_date(client):
    add_client(client)
    response = client.post("/pedidos/novo", data={
        "client_id": "1", "description": "Caixas", "order_date": "2026-10-15",
        "deadline": "2026-10-01", "value": "10", "status": "Pendente"
    })
    assert response.status_code == 400
    assert "O prazo não pode ser anterior" in response.get_data(as_text=True)


def test_status_can_be_updated(client):
    add_order(client)
    response = client.post("/pedidos/1/status", data={"status": "Em produção"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Em produção" in response.get_data(as_text=True)


def test_invalid_status_is_rejected(client):
    add_order(client)
    response = client.post("/pedidos/1/status", data={"status": "Cancelado"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Status inválido" in response.get_data(as_text=True)


def test_search_orders(client):
    add_order(client)
    response = client.get("/pedidos?q=Ana")
    assert response.status_code == 200
    assert "20 caixas personalizadas" in response.get_data(as_text=True)


def test_unknown_page_returns_404(client):
    response = client.get("/pagina-inexistente")
    assert response.status_code == 404
