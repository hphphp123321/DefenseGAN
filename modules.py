import numpy as np
from torch import nn
from torch.nn.utils import spectral_norm


# borrowed from https://github.com/pfnet-research/sngan_projection/blob/master/gen_models/resblocks.py
class ResBlockGenerator(nn.Module):
    def __init__(self, in_channels, out_channels, apply_sn=False):
        super().__init__()
        conv1 = nn.Conv2d(in_channels, out_channels, 3, padding=1)
        conv2 = nn.Conv2d(out_channels, out_channels, 3, padding=1)
        bypass_conv = nn.Conv2d(in_channels, out_channels, 1)
        nn.init.xavier_uniform_(conv1.weight.data, np.sqrt(2))
        nn.init.xavier_uniform_(conv2.weight.data, np.sqrt(2))
        nn.init.xavier_uniform_(bypass_conv.weight.data, 1.0)
        if apply_sn:
            conv1 = spectral_norm(conv1)
            conv2 = spectral_norm(conv2)
            bypass_conv = spectral_norm(bypass_conv)

        self.model = nn.Sequential(
            nn.BatchNorm2d(in_channels),
            nn.ReLU(),
            nn.Upsample(scale_factor=2),
            conv1,
            nn.BatchNorm2d(out_channels),
            nn.ReLU(),
            conv2
        )
        self.bypass = nn.Sequential(nn.Upsample(scale_factor=2), bypass_conv)

    def forward(self, x):
        return self.model(x) + self.bypass(x)


# borrowed from https://github.com/pfnet-research/sngan_projection/blob/master/dis_models/resblocks.py
class ResBlockDiscriminator(nn.Module):
    def __init__(self, in_channels, out_channels, apply_sn=False, is_first_layer=False):
        super().__init__()
        conv1 = nn.Conv2d(in_channels, in_channels, 3, padding=1)
        conv2 = nn.Conv2d(in_channels, out_channels, 3, padding=1)
        bypass_conv = nn.Conv2d(in_channels, out_channels, 1)
        nn.init.xavier_uniform_(conv1.weight.data, np.sqrt(2))
        nn.init.xavier_uniform_(conv2.weight.data, np.sqrt(2))
        nn.init.xavier_uniform_(bypass_conv.weight.data, 1.0)
        if apply_sn:
            conv1 = spectral_norm(conv1)
            conv2 = spectral_norm(conv2)
            bypass_conv = spectral_norm(bypass_conv)

        self.model = nn.Sequential(
            nn.Identity() if is_first_layer else nn.ReLU(),
            conv1,
            nn.ReLU(),
            conv2,
            nn.AvgPool2d(2)
        )
        self.bypass = nn.Sequential(bypass_conv, nn.AvgPool2d(2))

    def forward(self, x):
        return self.model(x) + self.bypass(x)


class ResNetGenerator(nn.Module):
    def __init__(self, z_dim=100, rgb_channels=1, dim=64, apply_sn=False):
        super().__init__()
        self.z_dim = z_dim
        self.dense = nn.Linear(z_dim, 2 * 2 * dim * 8)
        final = nn.Conv2d(dim, rgb_channels, 3, stride=1, padding=1)
        nn.init.xavier_uniform_(self.dense.weight.data, 1.)
        nn.init.xavier_uniform_(final.weight.data, 1.)
        if apply_sn:
            self.dense = spectral_norm(self.dense)
            final = spectral_norm(final)

        self.model = nn.Sequential(
            ResBlockGenerator(dim * 8, dim * 4, apply_sn),
            ResBlockGenerator(dim * 4, dim * 2, apply_sn),
            ResBlockGenerator(dim * 2, dim * 1, apply_sn),
            ResBlockGenerator(dim * 1, dim * 1, apply_sn),
            nn.BatchNorm2d(dim),
            nn.ReLU(),
            final,
            nn.Tanh()
        )

    def forward(self, z):
        return self.model(self.dense(z).view(z.size(0), -1, 2, 2))


class ResNetDiscriminator(nn.Module):
    def __init__(self, rgb_channels=1, dim=64, apply_sn=False):
        super().__init__()
        self.model = nn.Sequential(
            ResBlockDiscriminator(rgb_channels, dim, apply_sn, is_first_layer=True),
            ResBlockDiscriminator(dim, dim * 2, apply_sn),
            ResBlockDiscriminator(dim * 2, dim * 4, apply_sn),
            ResBlockDiscriminator(dim * 4, dim * 8, apply_sn),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d(1),
        )
        self.fc = nn.Linear(dim * 8, 1)
        nn.init.xavier_uniform_(self.fc.weight.data, 1.)
        if apply_sn:
            self.fc = spectral_norm(self.fc)

    def forward(self, x):
        return self.fc(self.model(x).view(x.size(0), -1))


# borrowed from https://github.com/pytorch/examples/blob/master/dcgan/main.py (modified to work on 32x32 images)
class DCGenerator(nn.Module):
    def __init__(self, z_dim=100, rgb_channels=1, dim=64, apply_sn=False):
        super().__init__()
        self.z_dim = z_dim
        self.apply_sn = apply_sn
        act = nn.ReLU()
        self.model = nn.Sequential(
            self.get_conv(z_dim, 8 * dim, 2, stride=1, padding=0),  # 2 * 2
            nn.BatchNorm2d(8 * dim),
            act,
            self.get_conv(8 * dim, 4 * dim, 4, stride=2, padding=1),  # 4 * 4
            nn.BatchNorm2d(4 * dim),
            act,
            self.get_conv(4 * dim, 2 * dim, 4, stride=2, padding=1),  # 8 * 8
            nn.BatchNorm2d(2 * dim),
            act,
            self.get_conv(2 * dim, dim, 4, stride=2, padding=1),  # 16 * 16
            nn.BatchNorm2d(dim),
            act,
            self.get_conv(dim, rgb_channels, 4, stride=2, padding=1),  # 32 * 32
            nn.Tanh(),
        )

    def get_conv(self, *args, **kwargs):
        conv = nn.ConvTranspose2d(*args, **kwargs, bias=False)
        if self.apply_sn:
            return spectral_norm(conv)
        return conv

    def forward(self, z):
        return self.model(z.view(-1, self.z_dim, 1, 1))


# borrowed from https://github.com/pytorch/examples/blob/master/dcgan/main.py (modified to work on 32x32 images)
# also removed the batch normalizations as suggested by many papers
class DCDiscriminator(nn.Module):
    def __init__(self, rgb_channels=1, dim=64, apply_sn=False):
        super().__init__()
        self.apply_sn = apply_sn
        act = nn.LeakyReLU(0.2)
        self.model = nn.Sequential(
            self.get_conv(rgb_channels, dim, 4, stride=2, padding=1),  # 16 x 16
            act,
            self.get_conv(dim, 2 * dim, 4, stride=2, padding=1),  # 8 * 8
            act,
            self.get_conv(2 * dim, 4 * dim, 4, stride=2, padding=1),  # 4 * 4
            act,
            self.get_conv(4 * dim, 8 * dim, 3, stride=2, padding=1),  # 2 * 2
            act,
        )
        self.fc = nn.Linear(2 * 2 * 8 * dim, 1)
        if self.apply_sn:
            self.fc = spectral_norm(self.fc)

    def get_conv(self, *args, **kwargs):
        conv = nn.Conv2d(*args, **kwargs, bias=False)
        if self.apply_sn:
            return spectral_norm(conv)
        return conv

    def forward(self, x):
        h = self.model(x).view(x.size(0), -1)
        return self.fc(h)
