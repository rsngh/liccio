def add(a, b):
    return a + b


def divide(a, b):
    if b == 0:
        return 0  # wrong: should raise ZeroDivisionError
    return a / b
