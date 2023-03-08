from inf349 import calculate_shipping_price


class TestOrder():
    def test_shipping_price(self):
        assert calculate_shipping_price(20) == 5
        assert calculate_shipping_price(0) == 5
        assert calculate_shipping_price(500) == 10
        assert calculate_shipping_price(1555) == 10
        assert calculate_shipping_price(2000) == 25
        assert calculate_shipping_price(5000) == 25
