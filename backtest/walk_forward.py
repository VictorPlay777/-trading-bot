def split_walk_forward(df, train_size=0.6, test_size=0.2, step=0.1):
    n = len(df)
    i = 0.0
    out = []
    while True:
        train_end = int((i + train_size) * n)
        test_end = int((i + train_size + test_size) * n)
        if test_end > n:
            break
        out.append((df.iloc[:train_end], df.iloc[train_end:test_end]))
        i += step
    return out

