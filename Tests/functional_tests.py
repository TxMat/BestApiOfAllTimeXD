from inf349 import db, Order, Product, ShippingInfo, Transaction, CreditCard, OrderProduct, populate_database


def init_db():
    db.connect()
    db.drop_tables([Product, ShippingInfo, Transaction, CreditCard, Order, OrderProduct])
    db.create_tables([Product, ShippingInfo, Transaction, CreditCard, Order, OrderProduct])
    populate_database()


class TestOrder():
    def test_populate_database(self):
        assert Product.select().count() == 50

    def test_create_order(self, client):
        # create order
        order = Order.create()
        assert order.id == 1
        assert order.shipping_info is None
        assert order.credit_card is None
        assert order.transaction is None
        assert order.order_products == []




