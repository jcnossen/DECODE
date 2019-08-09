from unittest import TestCase
import torch
import pytest
import matplotlib.pyplot as plt
from tensorboardX import SummaryWriter

import deepsmlm.test.utils_ci as tutil


from deepsmlm.generic.emitter import EmitterSet, CoordinateOnlyEmitter, RandomEmitterSet
import deepsmlm.neuralfitter.losscollection as loss


class TestFocalLoss:

    @pytest.fixture(scope='class')
    def focal(self):
        return loss.FocalLoss(focusing_param=2, balance_param=1.)
    
    @pytest.fixture(scope='class')
    def ce_loss(self):
        return torch.nn.CrossEntropyLoss()

    def test(self, ce_loss):
        gt = torch.zeros((2, 32)).type(torch.LongTensor)
        gt[0, 0] = 1

        prediction = torch.zeros((2, 2, 32))
        prediction[0, 0, 0] = 1.0
        prediction[0, 1, 0] = 1.0

        focal = loss.FocalLoss(focusing_param=0., balance_param=1.)
        l = focal.forward(prediction, gt)
        l_ce = ce_loss.forward(prediction, gt)

        assert tutil.tens_almeq(l, l_ce)

        focal_gamma2 = loss.FocalLoss(focusing_param=2.)
        l_2 = focal_gamma2.forward(prediction, gt)

        assert True


class TestSpeiserLogged:

    @pytest.fixture(scope='class')
    def crit(self):
        logger = SummaryWriter('temp', comment='dummy', write_to_disk=False)
        return loss.SpeiserLoss(False, logger=logger)

    def test_forward(self, crit):
        for _ in range(5):
            x = torch.rand((2, 5, 32, 32), requires_grad=True)
            gt = torch.rand_like(x)

            loss_ = crit(x, gt)
            loss_.mean().backward()

            crit.log_batch_loss_cmp(loss_)

        crit.log_components(1)
        assert True


class TestFocalVoronoiPointLoss:

    @pytest.fixture(scope='class')
    def fvp_loss(self):
        return loss.FocalVoronoiPointLoss(0.012, 0.9)

    @pytest.mark.skip("Skip.")
    def test_run(self, fvp_loss):
        gt = torch.zeros((2, 1, 32, 32))
        gt[0, 0, 0, 0] = 1

        prediction = gt.clone()
        prediction[0, 0, 0, 0] = 0.01

        loss = fvp_loss(prediction, gt)

        assert True