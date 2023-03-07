import json

import peewee
import requests
from flask import Flask, request
from playhouse.shortcuts import dict_to_model

import errors

app = Flask(__name__)

db = peewee.SqliteDatabase('lmao.db')


class BaseModel(peewee.Model):
    class Meta:
        database = db


class Product(BaseModel):
    id = peewee.IntegerField(primary_key=True, unique=True)
    name = peewee.CharField(max_length=255, null=False)
    type = peewee.CharField(max_length=255, null=False, constraints=[
        peewee.Check('type IN ("dairy", "vegetable", "fruit", "bakery", "vegan", "meat", "other")')])
    description = peewee.CharField()
    image = peewee.CharField()
    height = peewee.IntegerField(null=False, constraints=[peewee.Check('height >= 0')])
    weight = peewee.IntegerField(null=False, constraints=[peewee.Check('weight >= 0')])
    price = peewee.FloatField(null=False, constraints=[peewee.Check('price >= 0')])
    in_stock = peewee.BooleanField(null=False, default=False)


# shipping info model
class ShippingInfo(BaseModel):
    id = peewee.IntegerField(primary_key=True, unique=True)
    country = peewee.CharField(max_length=255, null=False)
    address = peewee.CharField(null=False)
    postal_code = peewee.CharField(max_length=7, null=False,
                                   constraints=[peewee.Check('postal_code LIKE "___ ___"')])
    city = peewee.CharField(max_length=255, null=False)
    province = peewee.CharField(max_length=255, null=False)


class Transaction(BaseModel):
    id = peewee.CharField(max_length=255, primary_key=True, unique=True)
    success = peewee.BooleanField(null=False, default=False)
    amount = peewee.FloatField(null=False, constraints=[peewee.Check('amount >= 0')])


class CreditCard(BaseModel):
    id = peewee.IntegerField(primary_key=True, unique=True)
    name = peewee.CharField(max_length=255, null=False)
    card_number = peewee.CharField(max_length=16, null=False,
                                   constraints=[peewee.Check('card_number LIKE "____ ____ ____ ____"')])
    expiration_date = peewee.DateField(null=False)
    cvv = peewee.CharField(max_length=3, null=False, constraints=[peewee.Check('cvv LIKE "___"')])


class Order(BaseModel):
    id = peewee.IntegerField(primary_key=True, unique=True)
    shipping_info_id = peewee.ForeignKeyField(ShippingInfo, backref='shipping_info', null=True)
    product_id = peewee.ForeignKeyField(Product, backref='product')
    email = peewee.CharField(max_length=255, constraints=[peewee.Check('email LIKE "%@%.%"')], null=True)
    paid = peewee.BooleanField(null=False, default=False)
    credit_card_id = peewee.ForeignKeyField(CreditCard, backref='credit_card', null=True)
    transaction_id = peewee.ForeignKeyField(Transaction, backref='transaction', null=True)


class OrderProduct(BaseModel):
    order_id = peewee.ForeignKeyField(Order, backref='order')
    product_id = peewee.ForeignKeyField(Product, backref='product')
    quantity = peewee.IntegerField(null=False, constraints=[peewee.Check('quantity >= 1')])


@app.route('/', methods=['GET'])
def display_products():
    products = Product.select()
    return json.dumps([product.__dict__['__data__'] for product in products])


@app.route('/order', methods=['POST'])
def order():
    try:
        product = request.json.get('product')
    except json.JSONDecodeError:
        return "Product is not a valid json", 400

    if product is None:
        return errors.error_handler("products", "missing-fields",
                                    "La creation d'une commande necessite un produit"), 422

    # check if product exists
    if Product.select().where(Product.id == product["id"]).count() == 0:
        return "Product does not exist", 400

    # check if product is in stock
    if Product.select().where(Product.id == product["id"], Product.in_stock).count() == 0:
        return errors.error_handler("products", "out-of-inventory", "Le produit demandé n'est pas en inventaire"), 422

    # check if quantity is valid
    if product["quantity"] < 1:
        return "Quantity is invalid", 400

    # create order
    try:
        new_order = Order.create(product_id=product["id"])
    except peewee.IntegrityError as e:
        print(e)
        return "Invalid order", 400

    try:
        OrderProduct.create(order_id=new_order.id, product_id=product["id"], quantity=product["quantity"])
    except peewee.IntegrityError as e:
        print(e)
        return "Invalid order", 400

    return "Order created", 200


@app.route('/order/<int:order_id>', methods=['GET'])
def get_order(order_id):
    odr = Order.select().where(Order.id == order_id)
    if odr.count() == 0:
        return "Order does not exist", 400

    odr = odr.get()
    odr = odr.__dict__['__data__']

    product = OrderProduct.select(OrderProduct.product_id, OrderProduct.quantity).where(
        OrderProduct.order_id == odr["id"])

    odr["product"] = {
        "id": product.get().product_id.id,
        "quantity": product.get().quantity
    }

    del odr["product_id"]

    # get shipping info from order.shipping_info_id
    try:
        odr["shipping_info"] = ShippingInfo.select().where(ShippingInfo.id == odr["shipping_info_id"]).get().__dict__[
            '__data__']
    except ShippingInfo.DoesNotExist:
        odr["shipping_info"] = {}

    del odr["shipping_info_id"]

    # get credit card from order.credit_card_id
    try:
        odr["credit_card"] = CreditCard.select().where(CreditCard.id == odr["credit_card_id"]).get().__dict__[
            '__data__']
    except CreditCard.DoesNotExist:
        odr["credit_card"] = {}

    del odr["credit_card_id"]

    # get transaction from order.transaction_id
    try:
        odr["transaction"] = Transaction.select().where(Transaction.id == odr["transaction_id"]).get().__dict__[
            '__data__']
    except Transaction.DoesNotExist:
        odr["transaction"] = {}

    del odr["transaction_id"]

    return json.dumps(odr)


def populate_database():
    # create products from url and add to database (only if database is empty)
    if Product.select().count() == 0:
        response = requests.get('http://dimprojetu.uqac.ca/~jgnault/shops/products/')
        products = json.loads(response.content)
        for product in products["products"]:
            print("Adding product: " + product["name"])
            product = dict_to_model(Product, product)
            # loops through all the fields in the model and sets them to the values in the dict
            try:
                Product.create(**product.__dict__['__data__'])
            except peewee.IntegrityError as e:
                print("invalid product: " + product.name)
                print("Error: " + str(e))


if __name__ == '__main__':
    db.connect()
    db.create_tables([Product, ShippingInfo, Transaction, CreditCard, Order, OrderProduct])
    populate_database()
    app.run()
