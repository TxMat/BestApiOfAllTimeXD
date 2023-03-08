import json

import peewee
import requests
from flask import Flask, request, redirect, url_for, jsonify
from playhouse.shortcuts import dict_to_model, model_to_dict

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
    amount_charged = peewee.FloatField(null=False, constraints=[peewee.Check('amount_charged >= 0')])


class CreditCard(BaseModel):
    id = peewee.IntegerField(primary_key=True, unique=True)
    name = peewee.CharField(max_length=255, null=False)
    card_number = peewee.CharField(max_length=16, null=False,
                                   constraints=[peewee.Check('card_number LIKE "____ ____ ____ ____"')])
    expiration_date = peewee.DateField(null=False)
    cvv = peewee.CharField(max_length=3, null=False, constraints=[peewee.Check('cvv LIKE "___"')])


class Order(BaseModel):
    id = peewee.IntegerField(primary_key=True, unique=True)
    shipping_info = peewee.ForeignKeyField(ShippingInfo, backref='shipping_info', null=True)
    product = peewee.ForeignKeyField(Product, backref='product')
    email = peewee.CharField(max_length=255, constraints=[peewee.Check('email LIKE "%@%.%"')], null=True)
    paid = peewee.BooleanField(null=False, default=False)
    credit_card = peewee.ForeignKeyField(CreditCard, backref='credit_card', null=True)
    transaction = peewee.ForeignKeyField(Transaction, backref='transaction', null=True)


# m2m table
class OrderProduct(BaseModel):
    order = peewee.ForeignKeyField(Order, backref='order')
    product = peewee.ForeignKeyField(Product, backref='product')
    quantity = peewee.IntegerField(null=False, constraints=[peewee.Check('quantity >= 1')])


@app.route('/', methods=['GET'])
def display_products():
    products = Product.select()
    return jsonify([model_to_dict(product) for product in products])


@app.route('/order', methods=['POST'])
def post_order():
    try:
        payload = request.json.get('product')
    except json.JSONDecodeError:
        return errors.error_handler("order", "json-not-valid", "Le json n\'est pas au bon format"), 422

    if not payload:
        return errors.error_handler("products", "missing-fields",
                                    "La création d'une commande nécessite un produit"), 422

    product_id = payload.get('id')
    quantity = payload.get('quantity')

    # check if product exists
    product = Product.get_or_none(Product.id == product_id)
    if not product:
        return errors.error_handler("order", "product-does-not-exist", "Le produit n'existe pas"), 404

    # check if product is in stock
    if not product.in_stock:
        return errors.error_handler("products", "out-of-inventory", "Le produit demandé n'est pas en inventaire"), 422

    # check if quantity is valid
    if quantity < 1:
        return errors.error_handler("order", "invalid-quantity", "La quantité ne peut pas être inférieure à 1"), 422

    # create order
    try:
        new_order = Order.create(product_id=product_id)
        OrderProduct.create(order_id=new_order.id, product_id=product_id, quantity=quantity)
    except peewee.IntegrityError as e:
        print(e)
        return errors.error_handler("order", "invalid-fields", "Les champs sont mal remplis"), 422

    # redirect to order/<id> page after creation
    return redirect(url_for('order_id_handler', order_id=new_order.id))


@app.route('/order/<int:order_id>', methods=['GET', 'PUT'])
def order_id_handler(order_id):
    def calculate_shipping_price(weight):
        if weight < 500:
            return 5
        elif weight < 2000:
            return 10
        else:
            return 25

    def get_order():
        # Check if order exists
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            return errors.error_handler("order", "order-does-not-exist", "L'order n'existe pas"), 404

        # Get order info
        order_dict = model_to_dict(order)

        # Get product info from order.product_id
        order_product = OrderProduct.get(OrderProduct.order_id == order.id)

        # Add product info to order
        order_dict["product"] = {
            "id": order_product.product.id,
            "quantity": order_product.quantity
        }

        # Add total price to order
        order_dict["total_price"] = order_product.product.price * order_product.quantity

        # Shipping price is calculated from product weight and quantity
        weight = order_product.quantity * order_product.product.weight

        order_dict["shipping_price"] = calculate_shipping_price(weight)

        # Get shipping info from order.shipping_info_id
        shipping_info = {}
        if order.shipping_info:
            shipping_info = model_to_dict(ShippingInfo.get_or_none(order.shipping_info.id))

        order_dict["shipping_info"] = shipping_info

        # Get credit card from order.credit_card_id
        credit_card = {}
        if order.credit_card:
            credit_card = model_to_dict(CreditCard.get_or_none(order.credit_card.id))

        order_dict["credit_card"] = credit_card

        # Get transaction from order.transaction_id
        transaction = {}
        if order.transaction:
            transaction = model_to_dict(Transaction.get_or_none(order.transaction.id))

        order_dict["transaction"] = transaction

        return jsonify({"order": order_dict})

    def put_order():

        def update_shipping_order(data):
            if not all(key in data for key in ("shipping_information", "email")):
                raise ValueError
            shipping_info = data["shipping_information"]
            if not all(key in shipping_info for key in ("address", "city", "province", "postal_code", "country")):
                return errors.error_handler("order", "missing-fields", "Il manque des champs dans le json"), 422

                # Check if shipping info exists
            if order.shipping_info:
                # Update shipping info instance
                shipping_info_instance = ShippingInfo.get_or_none(ShippingInfo.id == order.shipping_info.id)
                shipping_info_instance.update(**shipping_info).execute()
            else:
                # Create new shipping info instance
                try:
                    shipping_info_instance = ShippingInfo.create(**shipping_info)
                    order.shipping_info = shipping_info_instance.id
                except peewee.IntegrityError:
                    return errors.error_handler("orders", "invalid-fields",
                                                "Les informations d'achat ne sont pas correctes"), 400

            # Update order email and save
            order.email = data["email"]
            order.save()

            return get_order()

        def update_credit_card(data):
            if order.paid:
                return errors.error_handler("order", "already-paid", "La commande a deja ete payé"), 422

            if not all(key in data for key in ("name", "number", "expiration_year", "cvv", "expiration_month")):
                return errors.error_handler("credit-card", "missing-fields", "Il manque des champs dans le json"), 422

            if order.email is None or order.shipping_info is None:
                return errors.error_handler("order", "missing-fields",
                                            "Les informations du client sont nécessaire avant"
                                            " d'appliquer une carte de crédit"), 422

            if not (data["number"] == "4000 0000 0000 0002" or data["number"] == "4242 4242 4242 4242"):
                return errors.error_handler("credit-card", "incorrect-number", "Le numéro de carte est invalide"), 422

            order_product = OrderProduct.get_or_none(OrderProduct.order == order)

            if not order_product:
                return errors.error_handler("order", "unknown-error", "contactez l'administrateur du site"), 418  # :)
                # please don't remove this

            pay_payload = {
                "credit_card": {**data},
                "amount_charged": order_product.product.price * order_product.quantity + calculate_shipping_price(
                    order_product.product.weight * order_product.quantity),
            }

            # Send payment request
            response = requests.post("http://dimprojetu.uqac.ca/~jgnault/shops/pay/", json=pay_payload)

            if response.status_code == 200:
                # Create transaction
                transaction = Transaction.create(**response.json()["transaction"])
                order.transaction = transaction.id
                order.paid = True
                order.save()
            else:
                return response.json(), response.status_code

            return get_order()

        # Check if order exists
        order = Order.get_or_none(Order.id == order_id)

        if not order:
            return errors.error_handler("order", "order-not-found", "L'order n'existe pas"), 404

        try:
            # Check payload
            payload = request.json
            if "order" in payload:
                return update_shipping_order(payload["order"])
            elif "credit_card" in payload:
                return update_credit_card(payload["credit_card"])
        except (json.JSONDecodeError, ValueError):
            return errors.error_handler("order", "json-not-valid", "Le json n'est pas au bon format"), 422

    if request.method == 'GET':
        return get_order()
    elif request.method == 'PUT':
        return put_order()


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


@app.cli.command("init-db")
def init_db():
    db.connect()
    db.drop_tables([Product, ShippingInfo, Transaction, CreditCard, Order, OrderProduct])
    db.create_tables([Product, ShippingInfo, Transaction, CreditCard, Order, OrderProduct])
    populate_database()
