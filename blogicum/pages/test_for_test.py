def series_sum(incoming):
    # Конкатенирует все элементы списка, приводя их к строкам.
    result = ''
    for i in incoming:
        result += str(i)
    return result


incoming = [1, 7.0, 7]
print(series_sum(incoming))