import time
import torch
import torch.nn as nn
import torch.nn.functional as F
import matplotlib.pyplot as plt
import numpy as np
import math
from math import sqrt
import os
from pytorch_wavelets.dwt.transform1d import DWT1DForward, DWT1DInverse
from pytorch_wavelets.dwt.transform2d import DWTForward, DWTInverse
from torch.nn.functional import interpolate


def decor_time(func):
    def func2(*args, **kw):
        now = time.time()
        y = func(*args, **kw)
        t = time.time() - now
        print('call <{}>, time={}'.format(func.__name__, t))
        return y
    return func2


class AutoCorrelation(nn.Module):
    """
    AutoCorrelation Mechanism with the following two phases:
    (1) period-based dependencies discovery
    (2) time delay aggregation
    This block can replace the self-attention family mechanism seamlessly.
    """
    def __init__(self, mask_flag=True, factor=1, scale=None, attention_dropout=0.1, output_attention=False, configs=None):
        super(AutoCorrelation, self).__init__()
        print('Autocorrelation used !')
        self.factor = factor
        self.scale = scale
        self.mask_flag = mask_flag
        self.output_attention = output_attention
        self.dropout = nn.Dropout(attention_dropout)
        self.agg = None
        self.use_wavelet = configs.wavelet
        if self.use_wavelet:
            J = 3
            self.dwt1d = DWT1DForward(J=J, wave='db4')
            self.dwt1div = DWT1DInverse(wave='db4')
            self.j_list = [1, 2, 4, 8, 8]
            print('DWTCorrelation used, J={}, j_list={}'.format(J, self.j_list))

    # @decor_time
    def time_delay_agg_mzq(self, values, corr):
        head = values.shape[1]
        channel = values.shape[2]
        length = values.shape[3]
        S = length
        #  # else:
        values = values.transpose(2, 3)
        corr = corr.transpose(2, 3)
        top_k = int(round(self.factor * np.log(S)))
        # Rk = Rk.real
        # if version == 3:
        # V.size = [B, S, h]
        # S = V.shape[1]
        V_broad = torch.cat((values, values), dim=-2)  # size=[B, H, 2*S, h]
        V_rolled = V_broad.unfold(-2, S, 1)  # size=[B, H, S+1, h, S]
        # Rk.size = [B, S, h]
        Rk_kthsmallest = torch.kthvalue(corr, k=S - top_k, dim=-2, keepdim=True)  # size=[B, H, 1, h]
        mask = corr > torch.repeat_interleave(Rk_kthsmallest[0], repeats=S, dim=-2)
        corr = torch.softmax(corr * mask, dim=-1)  # size = [B, H, S, h]
        output = torch.einsum('beshi,besh->beih', V_rolled[:, :, 1:, :], corr)  # .transpose(1, 2)
        # [B, H, S+1, h, S] * [B, H, S, h]
        return output.transpose(2, 3)  # size=[batch, seq_len, h_dim]

    # @decor_time
    def time_delay_agg_training(self, values, corr):
        """
        SpeedUp version of Autocorrelation (a batch-normalization style design)
        This is for the training phase.
        """
        head = values.shape[1]
        channel = values.shape[2]
        length = values.shape[3]
        # find top k
        top_k = int(self.factor * math.log(length))
        mean_value = torch.mean(torch.mean(corr, dim=1), dim=1)
        index = torch.topk(torch.mean(mean_value, dim=0), top_k, dim=-1)[1]
        weights = torch.stack([mean_value[:, index[i]] for i in range(top_k)], dim=-1)
        # update corr
        tmp_corr = torch.softmax(weights, dim=-1)
        # aggregation
        tmp_values = values
        delays_agg = torch.zeros_like(values).float()
        for i in range(top_k):
            pattern = torch.roll(tmp_values, -int(index[i]), -1)
            delays_agg = delays_agg + pattern * \
                         (tmp_corr[:, i].unsqueeze(1).unsqueeze(1).unsqueeze(1).repeat(1, head, channel, length))
        return delays_agg  # size=[B, H, d, S]

    def time_delay_agg_inference(self, values, corr):
        """
        SpeedUp version of Autocorrelation (a batch-normalization style design)
        This is for the inference phase.
        """
        batch = values.shape[0]
        head = values.shape[1]
        channel = values.shape[2]
        length = values.shape[3]
        # index init
        init_index = torch.arange(length).unsqueeze(0).unsqueeze(0).unsqueeze(0).repeat(batch, head, channel, 1).cuda()
        # find top k
        top_k = int(self.factor * math.log(length))
        mean_value = torch.mean(torch.mean(corr, dim=1), dim=1)
        weights = torch.topk(mean_value, top_k, dim=-1)[0]
        delay = torch.topk(mean_value, top_k, dim=-1)[1]
        # update corr
        tmp_corr = torch.softmax(weights, dim=-1)
        # aggregation
        tmp_values = values.repeat(1, 1, 1, 2)
        delays_agg = torch.zeros_like(values).float()
        for i in range(top_k):
            tmp_delay = init_index + delay[:, i].unsqueeze(1).unsqueeze(1).unsqueeze(1).repeat(1, head, channel, length)
            pattern = torch.gather(tmp_values, dim=-1, index=tmp_delay)
            delays_agg = delays_agg + pattern * \
                         (tmp_corr[:, i].unsqueeze(1).unsqueeze(1).unsqueeze(1).repeat(1, head, channel, length))
        return delays_agg

    def time_delay_agg_full(self, values, corr):
        """
        Standard version of Autocorrelation
        """
        batch = values.shape[0]
        head = values.shape[1]
        channel = values.shape[2]
        length = values.shape[3]
        # index init
        init_index = torch.arange(length).unsqueeze(0).unsqueeze(0).unsqueeze(0).repeat(batch, head, channel, 1).cuda()
        # find top k
        top_k = int(self.factor * math.log(length))
        weights = torch.topk(corr, top_k, dim=-1)[0]
        delay = torch.topk(corr, top_k, dim=-1)[1]
        # update corr
        tmp_corr = torch.softmax(weights, dim=-1)
        # aggregation
        tmp_values = values.repeat(1, 1, 1, 2)
        delays_agg = torch.zeros_like(values).float()
        for i in range(top_k):
            tmp_delay = init_index + delay[..., i].unsqueeze(-1)
            pattern = torch.gather(tmp_values, dim=-1, index=tmp_delay)
            delays_agg = delays_agg + pattern * (tmp_corr[..., i].unsqueeze(-1))
        return delays_agg

    def forward(self, queries, keys, values, attn_mask):
        B, L, H, E = queries.shape
        _, S, _, D = values.shape
        if L > S:
            zeros = torch.zeros_like(queries[:, :(L - S), :]).float()
            values = torch.cat([values, zeros], dim=1)
            keys = torch.cat([keys, zeros], dim=1)
        else:
            values = values[:, :L, :, :]
            keys = keys[:, :L, :, :]

        # period-based dependencies
        if self.use_wavelet != 2:
            if self.use_wavelet == 1:
                j_list = self.j_list
                queries = queries.reshape([B, L, -1])
                keys = keys.reshape([B, L, -1])
                Ql, Qh_list = self.dwt1d(queries.transpose(1, 2))  # [B, H*D, L]
                Kl, Kh_list = self.dwt1d(keys.transpose(1, 2))
                # n = queries.shape[1]
                # B = queries.shape[0]
                qs = [queries.transpose(1, 2)] + Qh_list + [Ql]  # [B, H*D, L]
                ks = [keys.transpose(1, 2)] + Kh_list + [Kl]
                q_list = []
                k_list = []
                for q, k, j in zip(qs, ks, j_list):
                    q_list += [interpolate(q, scale_factor=j, mode='linear')[:, :, -L:]]
                    k_list += [interpolate(k, scale_factor=j, mode='linear')[:, :, -L:]]
                queries = torch.stack([i.reshape([B, H, E, L]) for i in q_list], dim=3).reshape([B, H, -1, L]).permute(0, 3, 1, 2)
                keys = torch.stack([i.reshape([B, H, E, L]) for i in k_list], dim=3).reshape([B, H, -1, L]).permute(0, 3, 1, 2)
            else:
                pass
            q_fft = torch.fft.rfft(queries.permute(0, 2, 3, 1).contiguous(), dim=-1)  # size=[B, H, E, L]
            k_fft = torch.fft.rfft(keys.permute(0, 2, 3, 1).contiguous(), dim=-1)
            res = q_fft * torch.conj(k_fft)
            corr = torch.fft.irfft(res, dim=-1) # size=[B, H, E, L]

            # time delay agg
            if self.training:
                # if self.agg == 'thuml':
                V = self.time_delay_agg_training(values.permute(0, 2, 3, 1).contiguous(), corr).permute(0, 3, 1, 2)  # [B, L, H, E], [B, H, E, L] -> [B, L, H, E]
                # elif self.agg == 'mzq':
                #     V = self.time_delay_agg_mzq(values.permute(0, 2, 3, 1).contiguous(), corr).permute(0, 3, 1, 2)
            else:
                V = self.time_delay_agg_inference(values.permute(0, 2, 3, 1).contiguous(), corr).permute(0, 3, 1, 2)

        else:
            V_list = []
            j_list = self.j_list
            queries = queries.reshape([B, L, -1])
            keys = keys.reshape([B, L, -1])
            values = values.reshape([B, L, -1])
            Ql, Qh_list = self.dwt1d(queries.transpose(1, 2))  # [B, H*D, L]
            Kl, Kh_list = self.dwt1d(keys.transpose(1, 2))
            Vl, Vh_list = self.dwt1d(values.transpose(1, 2))
            qs = Qh_list + [Ql]  # [B, H*D, L]
            ks = Kh_list + [Kl]
            vs = Vh_list + [Vl]
            for q, k, v in zip(qs, ks, vs):
                q = q.reshape([B, H, E, -1])
                k = k.reshape([B, H, E, -1])
                v = v.reshape([B, H, E, -1]).permute(0, 3, 1, 2)
                q_fft = torch.fft.rfft(q.contiguous(), dim=-1)
                k_fft = torch.fft.rfft(k.contiguous(), dim=-1)
                res = q_fft * torch.conj(k_fft)
                corr = torch.fft.irfft(res, dim=-1)  # [B, H, E, L]
                if self.training:
                    V = self.time_delay_agg_training(v.permute(0, 2, 3, 1).contiguous(), corr).permute(0, 3, 1, 2)
                else:
                    V = self.time_delay_agg_inference(v.permute(0, 2, 3, 1).contiguous(), corr).permute(0, 3, 1, 2)
                V_list += [V]
            Vl = V_list[-1].reshape([B, -1, H*E]).transpose(1, 2)
            Vh_list = [i.reshape([B, -1, H*E]).transpose(1, 2) for i in V_list[:-1]]
            V = self.dwt1div((Vl, Vh_list)).reshape([B, H, E, -1]).permute(0, 3, 1, 2)
            # corr = self.dwt1div((V_list[-1], V_list[:-1]))

        if self.output_attention:
            return (V.contiguous(), corr.permute(0, 3, 1, 2))  # size = [B, L, H, E]
        else:
            return (V.contiguous(), None)


class AutoCorrelationLayer(nn.Module):
    def __init__(self, correlation, d_model, n_heads, d_keys=None,
                 d_values=None):
        super(AutoCorrelationLayer, self).__init__()

        d_keys = d_keys or (d_model // n_heads)
        d_values = d_values or (d_model // n_heads)

        self.inner_correlation = correlation
        self.query_projection = nn.Linear(d_model, d_keys * n_heads)
        self.key_projection = nn.Linear(d_model, d_keys * n_heads)
        self.value_projection = nn.Linear(d_model, d_values * n_heads)
        self.out_projection = nn.Linear(d_values * n_heads, d_model)
        self.n_heads = n_heads

    def forward(self, queries, keys, values, attn_mask):
        B, L, _ = queries.shape
        _, S, _ = keys.shape
        H = self.n_heads

        queries = self.query_projection(queries).view(B, L, H, -1)
        keys = self.key_projection(keys).view(B, S, H, -1)
        values = self.value_projection(values).view(B, S, H, -1)

        out, attn = self.inner_correlation(
            queries,
            keys,
            values,
            attn_mask
        )

        out = out.view(B, L, -1)
        return self.out_projection(out), attn


if __name__ == '__main__':
    class Configs(object):
        wavelet = 2

    configs = Configs()
    B = 3
    H = 2
    S = 240
    d = 16
    x = torch.randn([B, S, H, d])
    model1 = AutoCorrelation(configs=configs)
    model1.training = 1
    model1.factor = 3
    # model1.agg = 'thuml'
    #
    # model2 = AutoCorrelation()
    # model2.training = 1
    # model2.factor = 3
    # model2.agg = 'mzq'
    out1 = model1.forward(x, x, x, 1)
    # out2 = model2.forward(x, x, x, 1)
    # diff = out1[0] - out2[0]

    # for S in 96, 480, 2400:
    #     print('========{}========='.format(S))
    #     x = torch.randn([B, S, H, d])
    #     for i in range(0, 3):
    #         out1 = model1.forward(x, x, x, 1)
    #         out2 = model2.forward(x, x, x, 1)
    a = 1