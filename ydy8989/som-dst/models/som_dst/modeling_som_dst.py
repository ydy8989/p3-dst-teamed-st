import torch.nn as nn
import torch
import torch.nn.functional as F
from transformers import AutoModel, ElectraModel
from transformers.modeling_utils import SequenceSummary
from modeling_bert import BertOnlyMLMHead


class SOMDST(nn.Module):
    """Some Information about SOMDST"""

    def __init__(self, config, n_domain, n_op, update_id):
        super(SOMDST, self).__init__()
        bert = AutoModel.from_pretrained(config.model_name_or_path)
        bert.resize_token_embeddings(config.vocab_size)
        self.n_domain = n_domain
        self.n_op = n_op
        self.encoder = BertEncoder(config, bert, self.n_domain, self.n_op, update_id)
        self.decoder = Decoder(
            config, self.encoder.bert.embeddings.word_embeddings.weight
        )

    def forward(
        self,
        input_ids,
        token_type_ids,
        slot_positions,
        attention_mask,
        max_value,
        op_ids=None,
        max_update=None,
        teacher=None,
    ):
        enc_outputs = self.encoder(
            input_ids=input_ids,
            token_type_ids=token_type_ids,
            state_positions=slot_positions,
            attention_mask=attention_mask,
            op_ids=op_ids,
            max_update=max_update,
        )
        (
            domain_scores,
            state_scores,
            decoder_inputs,
            sequence_output,
            pooled_output,
        ) = enc_outputs
        gen_scores = self.decoder(
            input_ids,
            decoder_inputs,
            sequence_output,
            pooled_output,
            max_value,
            teacher,
        )

        return domain_scores, state_scores, gen_scores

class SOMDST_pre(nn.Module):
    """Some Information about SOMDST"""

    def __init__(self, config, n_domain, n_op, update_id):
        super(SOMDST_pre, self).__init__()
        self.config = config
        bert = AutoModel.from_pretrained(config.model_name_or_path)
        bert.resize_token_embeddings(config.vocab_size)
        self.encoder = BertEncoder(config, bert, 5, 6, update_id)
        self.decoder = Decoder(
            config, self.encoder.bert.embeddings.word_embeddings.weight
        )
        self.mlm_head = BertOnlyMLMHead(config)

    def forward(
        self,
        input_ids,
        token_type_ids,
        slot_positions,
        attention_mask,
        max_value,
        op_ids=None,
        max_update=None,
        teacher=None,
    ):
        enc_outputs = self.encoder(
            input_ids=input_ids,#input_ids
            token_type_ids=token_type_ids,#segment_ids
            state_positions=slot_positions,#slot_position_ids
            attention_mask=attention_mask,#input_masks
            op_ids=op_ids,#gating_ids
            max_update=max_update,#max_update
        )
        (
            domain_scores,
            state_scores,
            decoder_inputs,
            sequence_output,
            pooled_output,
        ) = enc_outputs
        gen_scores = self.decoder(
            input_ids,
            decoder_inputs,
            sequence_output,
            pooled_output,
            max_value,
            teacher,
        )

        return domain_scores, state_scores, gen_scores

    @staticmethod
    def mask_tokens(inputs, tokenizer, config, mlm_probability=0.15):
        device = 'cuda'
        """ Prepare masked tokens inputs/labels for masked language modeling: 80% MASK, 10% random, 10% original. """
        labels = inputs.clone()
        # We sample a few tokens in each sequence for masked-LM training (with probability args.mlm_probability defaults to 0.15 in Bert/RoBERTa)
        probability_matrix = torch.full(labels.shape, mlm_probability).to(device)
        # special_tokens_mask = [tokenizer.get_special_tokens_mask(val, already_has_special_tokens=True) for val in labels.tolist()]

        probability_matrix.masked_fill_(torch.eq(labels, 0), value=0.0)

        masked_indices = torch.bernoulli(probability_matrix).bool()
        labels[~masked_indices] = -100  # We only compute loss on masked tokens

        # 80% of the time, we replace masked input tokens with tokenizer.mask_token ([MASK])
        indices_replaced = torch.bernoulli(torch.full(labels.shape, 0.8)).to(device=device,
                                                                             dtype=torch.bool) & masked_indices
        inputs[indices_replaced] = tokenizer.convert_tokens_to_ids(["[MASK]"])[0]

        # 10% of the time, we replace masked input tokens with random word
        indices_random = torch.bernoulli(torch.full(labels.shape, 0.5)).to(device=device,
                                                                           dtype=torch.bool) & masked_indices & ~indices_replaced
        random_words = torch.randint(config.vocab_size, labels.shape, device=device, dtype=torch.long)
        inputs[indices_random] = random_words[indices_random].to(device)

        # The rest of the time (10% of the time) we keep the masked input tokens unchanged
        return inputs, labels

    def forward_pretrain(self, input_ids, token_type_ids, slot_positions, attention_mask, tokenizer):
        input_ids, labels = self.mask_tokens(input_ids, tokenizer, self.config)
        encoder_outputs = self.encoder(input_ids=input_ids,
                                          token_type_ids = token_type_ids,
                                          state_positions = slot_positions,
                                          attention_mask = attention_mask)
        # print(encoder_outputs[0].shape,encoder_outputs[1].shape, encoder_outputs[2].shape, encoder_outputs[3].shape, encoder_outputs[4].shape)
        mlm_logits = self.mlm_head(encoder_outputs[3])
        # print(mlm_logits)
        return mlm_logits, labels

class BertEncoder(nn.Module):
    """Some Information about BertEncoder"""

    def __init__(self, config, bert, n_domain, n_op, update_id):
        super(BertEncoder, self).__init__()
        self.config = config
        self.n_op = n_op
        self.bert = bert
        self.hidden_size = config.hidden_size
        self.domain_classifier = nn.Linear(config.hidden_size, n_domain)
        self.op_classifier = nn.Linear(config.hidden_size, n_op)
        # self.electra = ElectraModel(config)
        self.sequence_summary = SequenceSummary(config)
        config.initializer_range = self.bert.config.initializer_range
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.update_id = update_id
        # self.maxselen = config.max_seq
    def forward(
        self,
        input_ids,
        token_type_ids,
        state_positions,
        attention_mask,
        op_ids=None,
        max_update=None,
    ):

        outputs = self.bert(
            input_ids=input_ids,
            token_type_ids=token_type_ids,
            attention_mask=attention_mask)
        # if self.config.arch_name=='bert':
        #bert
        sequence_output, pooled_output = outputs[:2]
        domain_scores = self.domain_classifier(self.dropout(pooled_output))
        # elif self.config.arch_name=='koelectra':
        #     #electra
        #     sequence_output = outputs[0]
        #     pooled_output = self.sequence_summary(sequence_output)
        #     domain_scores = self.domain_classifier(self.dropout(pooled_output))
        # state_positions: B x J
        # state_poas: B x J x H
        state_pos = state_positions[:, :, None].expand(-1, -1, sequence_output.size(-1))
        # state_output: B x J x H
        state_output = torch.gather(sequence_output, 1, state_pos)
        # state_scores: B x J x n_ops(4)
        state_scores = self.op_classifier(self.dropout(state_output))

        batch_size = state_scores.size(0)
        if op_ids is None:
            op_ids = state_scores.view(-1, self.n_op).max(-1)[-1].view(batch_size, -1)
        if max_update is None:
            max_update = op_ids.eq(self.update_id).sum(-1).max().item()
        gathered = []
        # Operation 이 Update 일 경우에 Value Generation 을 위한 Decoder Input 생성
        for b, a in zip(state_output, op_ids.eq(self.update_id)):
            if a.sum().item() != 0:  # J개의 Slot 중 Update가 1개 이상 존재한다면
                v = b.masked_select(a.unsqueeze(-1)).view(
                    1, -1, self.hidden_size
                )  # 1 x n_update x H
                n = v.size(1)  # num of Update
                gap = max_update - n
                if gap > 0:
                    # 부족한 개수만큼 패딩
                    zeros = torch.zeros(
                        1, 1 * gap, self.hidden_size, device=input_ids.device
                    )
                    v = torch.cat([v, zeros], 1)
            else:
                # Update 가 존재하지 않으면 dummy 값
                v = torch.zeros(
                    1, max_update, self.hidden_size, device=input_ids.device
                )
            gathered.append(v)
        decoder_inputs = torch.cat(gathered)  # B x max_update x H
        return (
            domain_scores,
            state_scores,
            decoder_inputs,
            sequence_output,
            pooled_output.unsqueeze(0),
        )


class Decoder(nn.Module):
    """Some Information about Decoder"""

    def __init__(self, config, bert_model_embedding_weights):
        super(Decoder, self).__init__()
        self.pad_idx = 0
        self.hidden_size = config.hidden_size
        self.vocab_size = config.vocab_size
        self.embed = nn.Embedding(config.vocab_size, config.hidden_size, padding_idx=0)
        self.embed.weight = bert_model_embedding_weights
        self.gru = nn.GRU(config.hidden_size, config.hidden_size, 1, batch_first=True, bidirectional=False)
        self.w_gen = nn.Linear(config.hidden_size * 3, 1)
        self.sigmoid = nn.Sigmoid()
        self.dropout = nn.Dropout(config.hidden_dropout_prob)

        for n, p in self.gru.named_parameters():
            if "weight" in n:
                p.data.normal_(mean=0.0, std=config.initializer_range)

    def forward(
        self, input_ids, decoder_inputs, encoder_output, hidden, max_value, teacher=None
    ):
        mask = input_ids.eq(self.pad_idx)
        batch_size, n_update, _ = decoder_inputs.size()

        state_in = decoder_inputs  # B x max_update x H

        # n_update x B x max_gen_lenth x vocab_size
        all_point_outputs = torch.zeros(
            n_update, batch_size, max_value, self.vocab_size, device=input_ids.device
        )

        for j in range(n_update):
            w = state_in[:, j].unsqueeze(1)  # B x 1 x H
            slot_value = []
            for k in range(max_value):
                w = self.dropout(w)
                _, hidden = self.gru(w, hidden)  # 1 x B x H
                attn_e = torch.bmm(encoder_output, hidden.permute(1, 2, 0))  # B x T x 1
                attn_e = attn_e.squeeze(-1).masked_fill(mask, -1e4)
                attn_history = nn.functional.softmax(attn_e, -1)  # B x T

                attn_v = torch.matmul(
                    hidden.squeeze(0), self.embed.weight.transpose(0, 1)
                )  # B x Vocab Size
                attn_vocab = nn.functional.softmax(attn_v, -1)

                context = torch.bmm(
                    attn_history.unsqueeze(1), encoder_output
                )  # B x 1 x H

                p_gen = self.sigmoid(
                    self.w_gen(torch.cat([w, hidden.transpose(0, 1), context], -1))
                )  # B x 1
                p_gen = p_gen.squeeze(-1)

                p_context_ptr = torch.zeros_like(attn_vocab, device=input_ids.device)
                p_context_ptr.scatter_add(
                    1, input_ids, attn_history
                )  # Copy: B x T -> B x V
                p_final = p_gen * attn_vocab + (1 - p_gen) * p_context_ptr  # B, V
                _, w_idx = p_final.max(-1)
                slot_value.append([ww.tolist() for ww in w_idx])
                if teacher is not None:
                    w = self.embed(teacher[:, j, k]).unsqueeze(1)
                else:
                    w = self.embed(w_idx).unsqueeze(1)
                all_point_outputs[j, :, k, :] = p_final
        return all_point_outputs.transpose(0, 1)
