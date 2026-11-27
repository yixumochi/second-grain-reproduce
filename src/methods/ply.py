

def ply(path,points,colors):
    with path.open('w',encoding='ascii') as f:
        f.write(f'ply\nformat ascii 1.0\nelement vertex {len(points)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n')
        for p,c in zip(points,colors): f.write(' '.join([*(f'{x:.6g}' for x in p),*(str(int(x)) for x in c)])+'\n')
