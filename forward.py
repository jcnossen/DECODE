import numpy as np
import torch
import torch.nn as nn
from torch.optim import Adam
from torch.utils.data import Dataset
from torch.utils.data import DataLoader
from torch.autograd import Variable
import matplotlib.pyplot as plt
plt.rcParams["figure.dpi"] = 4 * plt.rcParams["figure.dpi"]

from model import DeepSLMN
from train import SMLMDataset, load_model


def plot_frame(tensor):
    img = tensor.squeeze()
    plt.imshow(img, cmap='gray')


if __name__ == '__main__':
    data = SMLMDataset('data/test_32px_1e3_multiframe.npz', transform=['normalise'])
    model = load_model(file='network/3channel_smaller_kernel.pt')
    model.eval()
    num_examples = 2

    plt_rows = num_examples
    f, axarr = plt.subplots(plt_rows, 5)
    #f, axarr = plt.subplots(plt_rows, 3, gridspec_kw={'wspace':0.025, 'hspace':0.05})
    for i in range(num_examples):

        ran_ix = np.random.randint(data.__len__() - 1)
        print(ran_ix)
        input_image, target, _ = data.__getitem__(ran_ix)
        input_image, target = input_image.unsqueeze(0), target.unsqueeze(0)

        if torch.cuda.is_available():  # model_deep.cuda():
            input_image = input_image.cuda()
        output = model(input_image)

        for j in range(3):
            axarr[i, j].imshow(input_image[:, j, :, :].squeeze(), cmap='gray')
        axarr[i, 3].imshow(target.squeeze(), cmap='gray')
        axarr[i, 4].imshow(output.detach().numpy().squeeze(), cmap='gray')

        # hide labels
        for j in range(3):
            axarr[i, j].set_xticks([])
            axarr[i, j].set_xticks([])
            axarr[i, j].set_xticklabels([])
            axarr[i, j].set_yticklabels([])
            axarr[i, j].set_aspect('equal')
        axarr[i, 1].set_title('Input')
        axarr[i, 3].set_title('Target')
        axarr[i, 4].set_title('Output')
    plt.show()

    print('Done.')
