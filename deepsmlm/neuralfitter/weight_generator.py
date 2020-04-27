from abc import ABC, abstractmethod
from deprecated import deprecated
import torch
import torch.nn

import deepsmlm.generic.emitter as emc
import deepsmlm.simulation.psf_kernel as psf_kernel


class OneHotInflator:
    r"""
    Converts single hot px to ROI, i.e. inflates :math:`[0\ 0\ 1\ 0\ 0]` to :math:`[0\ 1\ 1\ 1\ 0]`
    The central pixel (the one hot) will always be preserved.

    Attributes:
        roi_size (int): size of inflation
        channels (int, tuple): channels to which the inflation should apply
        overlap_mode (str): overlap mode
    """

    _overlap_modes_all = ('zero', 'mean')

    def __init__(self, roi_size: int, channels, overlap_mode: str = 'zero'):
        """

        Args:
            roi_size (int): size of inflation
            channels (int, tuple): channels to which the inflation should apply
            overlap_mode (str, optional): overlap mode
        """
        self.roi_size = roi_size
        self.channels = channels
        self.overlap_mode = overlap_mode

        self._pad = torch.nn.ConstantPad2d(1, 0.)
        self._rep_kernel = torch.ones((channels, 1, self.roi_size, self.roi_size))

        """Sanity checks"""
        if self.roi_size != 3:
            raise NotImplementedError("Currently only ROI size 3 is implemented and tested.")

        if self.overlap_mode not in self._overlap_modes_all:
            raise NotImplementedError(f"Non supported overlap mode{self.overlap_mode}. Choose among: "
                                      f"{self._overlap_modes_all}")

    def _is_overlap(self, x):
        """
        Checks for every px whether it is going to be overlapped after inflation and returns the count

        Args:
            x:

        Returns:
            (torch.Tensor, torch.Tensor)
            is_overlap: boolean tensor
            xn_count: overlap count

        """
        # x non zero
        xn = torch.zeros_like(x)
        xn[x != 0] = 1.

        xn_count = torch.nn.functional.conv2d(self._pad(xn), self._rep_kernel, groups=self.channels).long()
        # xn_count *= xn
        is_overlap = xn_count >= 2.

        return is_overlap, xn_count

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forwards tensor through inflator and returns inflated result.

        Args:
            x (torch.Tensor): input

        Returns:
            torch.Tensor:   inflated result

        """

        xctr = x.clone()
        input = self._pad(x).clone()
        xrep = torch.nn.functional.conv2d(input, self._rep_kernel, groups=self.channels)
        overlap_mask, overlap_count = self._is_overlap(x)

        if self.overlap_mode == 'zero':
            xrep[overlap_mask] = 0.
        elif self.overlap_mode == 'mean':
            xrep[overlap_mask] /= overlap_count[overlap_mask]

        xrep[xctr != 0] = xctr[xctr != 0]
        return xrep


class WeightGenerator(ABC):
    """
    Abstract weight generator. A weight is something that is to be multiplied by the (non-reduced) loss, i.e. as

    """

    def __init__(self):
        super().__init__()
        self._squeeze_return = None

    @staticmethod
    def parse(param):
        """
        Constructs WeightGenerator by parameter variable which will be likely be a namedtuple, dotmap or similiar.
        
        Args:
            param:

        Returns:
            WeightGenerator: Instance of WeightGenerator child classes.

        """
        raise NotImplementedError

    def _forward_batched(self, x: torch.Tensor) -> torch.Tensor:
        """
        Returns x  in batched version if not already has batch dimension

        Args:
            x (torch.Tensor):

        Returns:
            torch.Tensor

        """

        if x.dim() == 3:
            x = x.unsqueeze(0)
            self._squeeze_return = True
        elif x.dim() == 4:
            self._squeeze_return = False
        else:
            raise ValueError("Unsupported shape.")
        return x

    def _forward_return_original(self, x: torch.Tensor) -> torch.Tensor:
        """
        Returns x in shape of what has been input to forward method

        Args:
            x (torch.Tensor):

        Returns:
            torch.Tensor

        """
        if self._squeeze_return:
            if x.size(0) != 1:
                raise ValueError("First, batch dimension, not singular.")
            return x.squeeze(0)
        else:
            return x

    @abstractmethod
    def forward(self, tar_frames: torch.Tensor, tar_em: emc.EmitterSet, tar_opt) -> torch.Tensor:
        """
        Forward frames, emitters and optional arguments through the weight generator.

        Args:
            tar_frames (torch.Tensor): frames of size :math:`((N,),C,H,W)`
            tar_em (EmitterSet): target EmitterSet
            tar_opt (optional): optional other arguments

        Returns:
            torch.Tensor: Weight mask of size :math:`((N,),D,H,W)` where likely :math:`C=D` but not necessarily.

        """
        if tar_frames.dim() not in (3, 4):
            raise ValueError("Unsupported shape of input.")

        return self._forward_batched(tar_frames)


class SimpleWeight(WeightGenerator):
    """
    Weight mask that is 1 in the detection and background channel everywhere and in the ROIs of the other detection
    channels. Assumes the following channel order prob (0), phot (1), x (2), y (3), z (4), bg (5).

    """

    _weight_bases_all = ('const', 'phot')

    def __init__(self, *, xextent: tuple, yextent: tuple, img_shape: tuple, target_roi_size: int,
                 weight_mode='const', weight_power: float = None):
        """

        Args:
            xextent (tuple): extent in x
            yextent (tuple): extent in y
            img_shape: image shape
            target_roi_size (int): roi size of the target
            weight_mode (str): constant or phot
            weight_power (float): power factor of the weight
        """
        super().__init__()

        self.target_roi_size = target_roi_size
        self.weight_psf = psf_kernel.DeltaPSF(xextent, yextent, img_shape, None)
        self.delta2roi = OneHotInflator(roi_size=self.target_roi_size,
                                        channels=4,
                                        overlap_mode='zero')

        self.weight_mode = weight_mode
        self.weight_power = weight_power if weight_power is not None else 1.0
        self._forward_safety = True  # safety checks in every forward pass

        """Sanity checks"""
        if self.weight_mode not in self._weight_bases_all:
            raise ValueError(f"Weight base must be in {self._weight_bases_all}.")

        if self.weight_mode == 'const' and self.weight_power != 1.:
            raise ValueError(f"Weight power of {self.weight_power} != 1."
                             f" which does not have an effect for constant weight mode")

    @staticmethod
    def parse(param):
        return SimpleWeight(xextent=param.Simulation.psf_extent[0], yextent=param.Simulation.psf_extent[1],
                            img_shape=param.Simulation.img_size, target_roi_size=param.HyperParameter.target_roi_size,
                            weight_mode=param.HyperParameter.weight_base,
                            weight_power=param.HyperParameter.weight_power)

    def forward(self, tar_frames: torch.Tensor, tar_em: emc.EmitterSet, tar_opt) -> torch.Tensor:
        tar_frames = super().forward(tar_frames, None, None)

        """Safety"""
        if self._forward_safety:
            if tar_frames.size(1) not in (5, 6):
                raise ValueError(f"Unsupported frame dimension {tar_frames.size()}. "
                                 f"Expected channel dimension to be 5 or 6.")

            if not tar_frames.size()[-2:] == torch.Size(self.weight_psf.img_shape):
                raise ValueError("Frame shape not according to init")

            if not (tar_em.phot >= 0.).all():
                raise ValueError(f"Photon count must be greater than zero.\nValues: {tar_em.phot}")

            if self.weight_mode == 'phot':
                if (tar_frames[:, [-1]] == 0).any():
                    raise ValueError("bg must all non 0.")

        """Detection and Background channel"""
        weight = torch.zeros_like(tar_frames)
        weight[:, 0] = 1.
        if weight.size(1) == 6:
            weight[:, 5] = 1.

        if len(tar_em) == 0:  # no target emitter can be returned here after basic init of the weight mask
            return self._forward_return_original(weight)

        if self.weight_mode == 'const':
            weight_pxyz = self.weight_psf.forward(tar_em.xyz, torch.ones_like(tar_em.xyz[:, 0]))
            weight[:, 1:5] = weight_pxyz.unsqueeze(1).repeat(1, 4, 1, 1)

        elif self.weight_mode == 'phot':
            """Simple approximation to the CRLB. """
            weight_phot = self.weight_psf.forward(tar_em.xyz, 1 / tar_em.phot ** self.weight_power)
            weight_xyz = self.weight_psf.forward(tar_em.xyz, tar_em.phot ** self.weight_power)
            weight_pxyz = torch.cat((weight_phot, weight_xyz.repeat(3, 1, 1)), 0).unsqueeze(0)
            weight[:, 1:5] = weight_pxyz
            if weight.size(1) == 6:  # weight of background, CRLB approximation similiar to photon
                weight[:, 5] *= 1 / tar_frames[:, 5] ** self.weight_power

        weight[:, 1:5] = self.delta2roi.forward(weight[:, 1:5])
        return self._forward_return_original(weight)  # return in dimensions of input frame


@deprecated(version="0.1.dev", reason="Not used. Write a test before reactivating.")
class CalcCRLB(WeightGenerator):
    def __init__(self, psf, crlb_mode):
        """

        Args:
            psf: (psf)
            crlb_mode: ('single', 'multi') single assumes isolated emitters
        """
        super().__init__()
        self.crlb_mode = crlb_mode
        self.psf = psf

    def forward(self, tar_frames, tar_em, tar_bg):
        """
        Wrapper that writes crlb values to target emitter set. Not of use outside training

        Args:
            tar_frames:
            tar_em:
            tar_bg:

        Returns:

        """
        tar_em.populate_crlb(self.psf, mode=self.crlb_mode)
        return tar_frames, tar_em, tar_bg


@deprecated(version="0.1.dev", reason="Not used. Write a test before reactivating.")
class GenerateWeightMaskFromCRLB(WeightGenerator):
    def __init__(self, xextent, yextent, img_shape, roi_size, chwise_rescale=True):
        super().__init__()

        self.weight_psf = psf_kernel.DeltaPSF(xextent, yextent, img_shape, None)
        self.rep_kernel = torch.ones((1, 1, roi_size, roi_size))

        self.roi_increaser = OneHotInflator(roi_size, channels=6, overlap_mode='zero')
        self.chwise_rescale = chwise_rescale

    def forward(self, tar_frames, tar_em, tar_bg):

        if tar_frames.dim() == 3:
            tar_frames = tar_frames.unsqueeze(0)
            squeeze_return = True
        else:
            squeeze_return = False

        # The weights
        weight = torch.zeros((tar_frames.size(0), 6, tar_frames.size(2), tar_frames.size(3)))
        weight[:, 1] = self.weight_psf.forward(tar_em.xyz, 1 / tar_em.phot_cr)
        weight[:, 2] = self.weight_psf.forward(tar_em.xyz, 1 / tar_em.xyz_cr[:, 0])
        weight[:, 3] = self.weight_psf.forward(tar_em.xyz, 1 / tar_em.xyz_cr[:, 1])
        weight[:, 4] = self.weight_psf.forward(tar_em.xyz, 1 / tar_em.xyz_cr[:, 2])

        weight = self.roi_increaser.forward(weight)
        weight[:, 0] = 1.
        weight[:, 5] = 1.

        if squeeze_return:
            return weight.squeeze(0)
        else:
            return weight

