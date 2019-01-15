import math
import numpy as np
import os
import torch


def repeat_np(a, repeats, dim):
    """
    Substitute for numpy's repeat function. Taken from https://discuss.pytorch.org/t/how-to-tile-a-tensor/13853/2
    torch.repeat([1,2,3], 2) --> [1, 2, 3, 1, 2, 3]
    np.repeat([1,2,3], repeats=2, axis=0) --> [1, 1, 2, 2, 3, 3]

    :param a: tensor
    :param repeats: number of repeats
    :param dim: dimension where to repeat
    :return: tensor with repitions
    """

    init_dim = a.size(dim)
    repeat_idx = [1] * a.dim()
    repeat_idx[dim] = repeats
    a = a.repeat(*(repeat_idx))
    if a.is_cuda:  # use cuda-device if input was on cuda device already
        order_index = torch.cuda.LongTensor(
            torch.cat([init_dim * torch.arange(repeats, device=a.device) + i for i in range(init_dim)]))
    else:
        order_index = torch.LongTensor(
            torch.cat([init_dim * torch.arange(repeats) + i for i in range(init_dim)]))

    return torch.index_select(a, dim, order_index)


def get_free_gpu(safety_factor=0.8):
    """
    https://discuss.pytorch.org/t/it-there-anyway-to-let-program-select-free-gpu-automatically/17560/7
    """
    if torch.cuda.is_available():
        os.system('nvidia-smi -q -d Memory |grep -A4 GPU|grep Free >tmp')
        memory_available = [int(x.split()[2]) for x in open('tmp', 'r').readlines()]
        return np.argmax(memory_available), np.max(memory_available) * 10**6 * safety_factor
    else:
        return None


def memory_of_tensor(a):
    return a.element_size() * a.nelement()


def splitbatchandrunfunc(b_vector, func, func_args, batch_size_target=None, to_cuda=False):
    if batch_size_target is None:
        b_vector_mem = memory_of_tensor(b_vector)
        _, free_mem = get_free_gpu()
        if free_mem > b_vector_mem:
            batch_size_target = b_vector.shape[0]
        else:
            batch_size_target = math.floor(free_mem / b_vector_mem * b_vector.shape[0])

    b_vector_split = torch.split(b_vector, batch_size_target)
    out = [None] * b_vector_split.__len__()
    for i in range(b_vector_split.__len__()):
        if to_cuda:
            out[i] = func(b_vector_split[i].cuda(), *func_args).cpu()
        else:
            out[i] = func(b_vector_split[i], *func_args)
    return torch.cat(out, 0)


def kron(t1, t2):
    """
    Taken from: https://discuss.pytorch.org/t/kronecker-product/3919/4
    Computes the Kronecker product between two tensors.
    See https://en.wikipedia.org/wiki/Kronecker_product
    """
    t1_height, t1_width = t1.size()
    t2_height, t2_width = t2.size()
    out_height = t1_height * t2_height
    out_width = t1_width * t2_width

    tiled_t2 = t2.repeat(t1_height, t1_width)
    expanded_t1 = (t1.unsqueeze(2).unsqueeze(3).repeat(1, t2_height, t2_width, 1).view(out_height, out_width))

    return expanded_t1 * tiled_t2


if __name__ == '__main__':
    x = torch.rand(8, 2)
    print(x)
    print(splitbatchandrunfunc(x, lambda x: x + 2, [], None), True)