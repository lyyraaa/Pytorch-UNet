""" Full assembly of the parts to form the complete network """

from .unet_parts import *


class UNet(nn.Module):
    def __init__(self, n_channels, n_classes, bilinear=False):
        super(UNet, self).__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.bilinear = bilinear

        self.inc = (DoubleConv(n_channels, 64))
        self.down1 = (Down(64, 128))
        self.down2 = (Down(128, 256))
        self.down3 = (Down(256, 512))
        factor = 2 if bilinear else 1
        self.down4 = (Down(512, 1024 // factor))
        self.up1 = (Up(1024, 512 // factor, bilinear))
        self.up2 = (Up(512, 256 // factor, bilinear))
        self.up3 = (Up(256, 128 // factor, bilinear))
        self.up4 = (Up(128, 64, bilinear))
        self.outc = (OutConv(64, n_classes))

    def forward(self, x):
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)
        x = self.up1(x5, x4)
        x = self.up2(x, x3)
        x = self.up3(x, x2)
        x = self.up4(x, x1)
        logits = self.outc(x)
        return logits

    def use_checkpointing(self):
        self.inc = torch.utils.checkpoint(self.inc)
        self.down1 = torch.utils.checkpoint(self.down1)
        self.down2 = torch.utils.checkpoint(self.down2)
        self.down3 = torch.utils.checkpoint(self.down3)
        self.down4 = torch.utils.checkpoint(self.down4)
        self.up1 = torch.utils.checkpoint(self.up1)
        self.up2 = torch.utils.checkpoint(self.up2)
        self.up3 = torch.utils.checkpoint(self.up3)
        self.up4 = torch.utils.checkpoint(self.up4)
        self.outc = torch.utils.checkpoint(self.outc)

class CompSegNet(nn.Module):
    def __init__(self, n_channels, n_classes, alpha=0.1,beta=0.8,dropout=0.0, bilinear=False):
        super(CompSegNet, self).__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.bilinear = bilinear

        self.alpha = alpha
        self.beta = beta
        self.dropout = nn.Dropout(p=dropout)

        self.inc = (DoubleConv(n_channels, 64))
        self.down1 = (Down(64, 128))
        self.down2 = (Down(128, 256))
        self.down3 = (Down(256, 512))
        factor = 2 if bilinear else 1
        self.down4 = (Down(512, 1024 // factor))
        self.up1 = (Up(1024, 512 // factor, bilinear))
        self.up2 = (Up(512, 256 // factor, bilinear))
        self.up3 = (Up(256, 128 // factor, bilinear))
        self.up4 = (Up(128, 64, bilinear))
        self.outc = (OutConv(64, n_classes))
        self.sigmoid = torch.nn.Sigmoid()

    def trans_sigmoid(self,x):
        act_0 = (x <= self.alpha) * (x/self.alpha)
        act_1 = torch.logical_and(self.alpha < x , x <= self.alpha + self.beta) * 1.0
        act_2 = (x > self.alpha+self.beta) * ((1-x)/(1 - (self.alpha+self.beta)))
        activation_sum = act_0+act_1+act_2
        activation_sum[x > 1] = 0
        activation_sum[x < 0] = 0

        return activation_sum

    def forward(self, x, tissue_mask = False):
        if type(tissue_mask) == bool:
            tissue_px = torch.count_nonzero(x,axis=(1,2,3))/x.shape[1]
        else:
            tissue_px = torch.count_nonzero(tissue_mask,axis=(2,3)).squeeze()

        x1 = self.inc(x)
        self.dropout(x1)
        x2 = self.down1(x1)
        self.dropout(x2)
        x3 = self.down2(x2)
        self.dropout(x3)
        x4 = self.down3(x3)
        self.dropout(x4)
        x5 = self.down4(x4)
        self.dropout(x5)
        x = self.up1(x5, x4)
        self.dropout(x)
        x = self.up2(x, x3)
        self.dropout(x)
        x = self.up3(x, x2)
        self.dropout(x)
        x = self.up4(x, x1)
        self.dropout(x)
        logits = self.outc(x)
        sig = self.sigmoid(logits)
        pool = torch.sum(sig,dim=(2,3)).squeeze()
        pool_frac = torch.div(pool,tissue_px)
        trans_sig = self.trans_sigmoid(pool_frac)
        return trans_sig, sig

class CompSegNetGrader(nn.Module):
    def __init__(self, n_channels, n_classes, alpha=0.1, beta=0.8, dropout=0.0, bilinear=False, softmax=True):
        super(CompSegNetGrader, self).__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.bilinear = bilinear
        self.softmax = softmax

        self.alpha = alpha
        self.beta = beta
        self.dropout = nn.Dropout(p=dropout)

        self.inc = (DoubleConv(n_channels, 64))
        self.down1 = (Down(64, 128))
        self.down2 = (Down(128, 256))
        self.down3 = (Down(256, 512))
        factor = 2 if bilinear else 1
        self.down4 = (Down(512, 1024 // factor))
        self.up1 = (Up(1024, 512 // factor, bilinear))
        self.up2 = (Up(512, 256 // factor, bilinear))
        self.up3 = (Up(256, 128 // factor, bilinear))
        self.up4 = (Up(128, 64, bilinear))
        self.outc = (OutConv(64, n_classes))
        self.sigmoid = torch.nn.Sigmoid()

    def forward(self, x, cancer_mask):
        # Contracting path
        x1 = self.inc(x)
        self.dropout(x1)
        x2 = self.down1(x1)
        self.dropout(x2)
        x3 = self.down2(x2)
        self.dropout(x3)
        x4 = self.down3(x3)
        self.dropout(x4)
        x5 = self.down4(x4)
        self.dropout(x5)

        # Expanding Path
        x = self.up1(x5, x4)
        self.dropout(x)
        x = self.up2(x, x3)
        self.dropout(x)
        x = self.up3(x, x2)
        self.dropout(x)
        x = self.up4(x, x1)
        self.dropout(x)

        # Activation layer
        logits = self.outc(x)
        sig = self.sigmoid(logits)

        grade_activations = sig
        if self.softmax:
            grade_activations = torch.nn.functional.softmax(sig, dim=1)

        return grade_activations

class CompSegNet_3net(nn.Module):
    def __init__(self, n_channels, n_classes, alpha=0.1,beta=0.8,dropout=0.0, bilinear=False):
        super(CompSegNet_3net, self).__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.bilinear = bilinear

        self.alpha = alpha
        self.beta = beta
        self.dropout = nn.Dropout(p=dropout)

        self.inc = (DoubleConv(n_channels, 64))
        self.down1 = (Down(64, 128))
        self.down2 = (Down(128, 256))
        self.down3 = (Down(256, 512))
        factor = 2 if bilinear else 1
        self.down4 = (Down(512, 1024 // factor))
        self.up1 = (Up(1024, 512 // factor, bilinear))
        self.up2 = (Up(512, 256 // factor, bilinear))
        self.up3 = (Up(256, 128 // factor, bilinear))
        self.up4 = (Up(128, 64, bilinear))
        self.outc = (OutConv(64, n_classes))
        self.sigmoid = torch.nn.Sigmoid()

    def trans_sigmoid(self,x):
        act_0 = (x <= self.alpha) * (x/self.alpha)
        act_1 = torch.logical_and(self.alpha < x , x <= self.alpha + self.beta) * 1.0
        act_2 = (x > self.alpha+self.beta) * ((1-x)/(1 - (self.alpha+self.beta)))
        activation_sum = act_0+act_1+act_2
        activation_sum[x > 1] = 0
        activation_sum[x < 0] = 0

        return activation_sum

    def forward(self, x, tissue_mask):
        tissue_px = torch.count_nonzero(tissue_mask,axis=(2,3)).squeeze()

        x1 = self.inc(x)
        self.dropout(x1)
        x2 = self.down1(x1)
        self.dropout(x2)
        x3 = self.down2(x2)
        self.dropout(x3)
        x4 = self.down3(x3)
        self.dropout(x4)
        x5 = self.down4(x4)
        self.dropout(x5)
        x = self.up1(x5, x4)
        self.dropout(x)
        x = self.up2(x, x3)
        self.dropout(x)
        x = self.up3(x, x2)
        self.dropout(x)
        x = self.up4(x, x1)
        self.dropout(x)
        logits = self.outc(x)
        sig = self.sigmoid(logits)
        pool = torch.sum(sig,dim=(2,3)).squeeze()
        pool_frac = torch.div(pool,tissue_px)
        trans_sig = self.trans_sigmoid(pool_frac)
        return trans_sig, pool_frac, sig
