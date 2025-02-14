import argparse
import json
import os
import random
import pickle
import glob
from pathlib import Path
import re

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, RandomSampler, SequentialSampler
from tqdm import tqdm
from transformers import AdamW, BertTokenizer, get_linear_schedule_with_warmup

from pytorch_transformers import WarmupLinearSchedule

from data_utils import WOSDataset, get_examples_from_dialogues, load_dataset, set_seed
from evaluation import _evaluation
from inference_somdst import inference
from model import SOMDST
from preprocessor import SOMDSTPreprocessor

import torch.cuda.amp as amp
import wandb

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def masked_cross_entropy_for_value(logits, target, pad_idx=0):
    mask = target.ne(pad_idx)
    logits_flat = logits.view(-1, logits.size(-1))
    log_probs_flat = torch.log(logits_flat)
    target_flat = target.view(-1, 1)
    losses_flat = -torch.gather(log_probs_flat, dim=1, index=target_flat)
    losses = losses_flat.view(*target.size())
    losses = losses * mask.float()
    loss = losses.sum() / (mask.sum().float())
    return loss

def increment_path(path, exist_ok=False):
    """Automatically increment path, i.e. runs/exp --> runs/exp0, runs/exp1 etc.

    Args:
        path (str or pathlib.Path): f"{model_dir}/{args.name}".
        exist_ok (bool): whether increment path (increment if False).
    """
    path = Path(path)
    if (path.exists() and exist_ok) or (not path.exists()):
        return str(path)
    else:
        dirs = glob.glob(f"{path}*")
        matches = [re.search(rf"%s(\d+)" % path.stem, d) for d in dirs]
        i = [int(m.groups()[0]) for m in matches if m]
        n = max(i) + 1 if i else 2
        return f"{path}{n}"


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--run_name", type=str, default="SOMDST")
    parser.add_argument("--data_dir", type=str, default="/opt/ml/code/ekzm8523/somdst/somdst_data/")
    parser.add_argument("--model_dir", type=str, default="/opt/ml/output")
    parser.add_argument("--model_name", type=str, default="")
    parser.add_argument("--ckpt", type=int, default=24)
    parser.add_argument("--train_batch_size", type=int, default=16)
    parser.add_argument("--eval_batch_size", type=int, default=32)

    parser.add_argument("--learning_rate", type=float, default=1e-5)
    # parser.add_argument("--enc_lr", type=float, default=1e-5)
    # parser.add_argument("--dec_lr", type=float, default=2e-5)
    # parser.add_argument("--enc_warmup", type=float, default=0.1)
    # parser.add_argument("--dec_warmup", type=float, default=0.1)

    parser.add_argument("--adam_epsilon", type=float, default=1e-4)
    parser.add_argument("--max_grad_norm", type=float, default=1.0)
    parser.add_argument("--num_train_epochs", type=int, default=50)
    parser.add_argument("--warmup_ratio", type=float, default=0.1)
    parser.add_argument("--random_seed", type=int, default=42)
    parser.add_argument("--max_seq_length", type=int, default=512)
    parser.add_argument("--model_name_or_path", type=str, default="dsksd/bert-ko-small-minimal",)

    # Model Specific Argument
    parser.add_argument("--hidden_size", type=int, help="GRU의 hidden size", default=768)
    parser.add_argument("--vocab_size", type=int, default=None)
    parser.add_argument("--hidden_dropout_prob", type=float, default=0.1)
    parser.add_argument("--proj_dim", type=int, default=None,)
    parser.add_argument("--teacher_forcing_ratio", type=float, default=0.5)
    parser.add_argument("--wandb_name", type=str, default=None)

    args = parser.parse_args()
    save = False
    if args.wandb_name:
        save_dir = f"{args.model_dir}/{args.wandb_name}"
        save = True
        save_dir = increment_path(save_dir)

    set_seed(args.random_seed)

    # Data Loading
    slot_meta = json.load(open("/opt/ml/input/data/train_dataset/slot_meta.json"))
    tokenizer = BertTokenizer.from_pretrained(args.model_name_or_path)
    added_token_num = tokenizer.add_special_tokens(
        {"additional_special_tokens": ["[SLOT]", "[NULL]", "[EOS]"]}
    )
    # Define Preprocessor
    processor = SOMDSTPreprocessor(
        slot_meta, tokenizer, max_seq_length=args.max_seq_length
    )
    args.vocab_size = tokenizer.vocab_size + added_token_num
    # args.n_gate = len(processor.gating2id)  # gating 갯수 none, dontcare, ptr

    if not os.path.exists(os.path.join(args.data_dir, "train_somdst_features.pkl")):
        print("Cached Input Features not Found.\nLoad data and save.")

        train_data_file = "/opt/ml/input/data/train_dataset/train_dials.json"
        train_data, dev_data, dev_labels = load_dataset(train_data_file)
        train_examples = get_examples_from_dialogues(
            train_data, user_first=False, dialogue_level=False
        )
        dev_examples = get_examples_from_dialogues(
            dev_data, user_first=False, dialogue_level=False
        )

        # Extracting Featrues
        train_features = processor.convert_examples_to_features(train_examples)
        print("Save Data")
        with open(os.path.join(args.data_dir, "train_somdst_features.pkl"), "wb") as f:
            pickle.dump(train_features, f)
        with open(os.path.join(args.data_dir, "dev_somdst_examples.pkl"), "wb") as f:
            pickle.dump(dev_examples, f)
        with open(os.path.join(args.data_dir, "dev_somdst_labels.pkl"), "wb") as f:
            pickle.dump(dev_labels, f)
    else:
        print("Cached Input Features Found.\nLoad data from Cached")
        with open(os.path.join(args.data_dir, "train_somdst_features.pkl"), "rb") as f:
            train_features = pickle.load(f)
        with open(os.path.join(args.data_dir, "dev_somdst_examples.pkl"), "rb") as f:
            dev_examples = pickle.load(f)
        with open(os.path.join(args.data_dir, "dev_somdst_labels.pkl"), "rb") as f:
            dev_labels = pickle.load(f)

    # Model 선언
    model = SOMDST(args, 5, 4, processor.op2id["update"])

    if save:
        wandb.init(project='pstage3', entity='ekzm8523')
        wandb.config.update(args)
        wandb.run.name = args.wandb_name
        wandb.watch(model)
    if args.model_name:
        print("Checkpoint Load")
        ckpt = torch.load(os.path.join(args.model_name))
        model.load_state_dict(ckpt)

    # model.set_subword_embedding(args.model_name_or_path)  # Subword Embedding 초기화
    # print(f"Subword Embeddings is loaded from {args.model_name_or_path}")
    model.to(device)
    print("Model is initialized")

    train_data = WOSDataset(train_features)
    train_sampler = RandomSampler(train_data)
    train_loader = DataLoader(
        train_data,
        batch_size=args.train_batch_size,
        sampler=train_sampler,
        collate_fn=processor.collate_fn,
        num_workers=4,
    )
    print("# train:", len(train_data))

    print("# dev:", len(dev_examples))

    # Optimizer 및 Scheduler 선언
    n_epochs = args.num_train_epochs
    t_total = len(train_loader) * n_epochs
    warmup_steps = int(t_total * args.warmup_ratio)
    optimizer = AdamW(model.parameters(), lr=args.learning_rate, eps=args.adam_epsilon)
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=t_total
    )
    #
    # num_train_steps = int(len(train_loader) / args.train_batch_size * n_epochs)
    #
    # no_decay = ['bias', 'LayerNorm.bias', 'LayerNorm.weight']
    # enc_param_optimizer = list(model.encoder.named_parameters())
    # enc_optimizer_grouped_parameters = [
    #     {'params': [p for n, p in enc_param_optimizer if not any(nd in n for nd in no_decay)], 'weight_decay': 0.01},
    #     {'params': [p for n, p in enc_param_optimizer if any(nd in n for nd in no_decay)], 'weight_decay': 0.0}
    # ]
    #
    # enc_optimizer = AdamW(enc_optimizer_grouped_parameters, lr=args.enc_lr)
    # enc_scheduler = WarmupLinearSchedule(enc_optimizer, int(num_train_steps * args.enc_warmup),
    #                                      t_total=num_train_steps)
    #
    # dec_param_optimizer = list(model.decoder.parameters())
    # dec_optimizer = AdamW(dec_param_optimizer, lr=args.dec_lr)
    # dec_scheduler = WarmupLinearSchedule(dec_optimizer, int(num_train_steps * args.dec_warmup),
    #                                      t_total=num_train_steps)


    loss_fnc_1 = masked_cross_entropy_for_value  # generation
    loss_fnc_2 = nn.CrossEntropyLoss()  # gating

    if save:
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)

        json.dump(
            vars(args),
            open(f"{save_dir}/exp_config.json", "w"),
            indent=2,
            ensure_ascii=False,
        )
        json.dump(
            slot_meta,
            open(f"{save_dir}/slot_meta.json", "w"),
            indent=2,
            ensure_ascii=False,
        )

    idx = 0
    best_score, best_checkpoint = 0, 0
    for epoch in range(n_epochs):

        model.train()
        for step, batch in enumerate(tqdm(train_loader)):

            batch = [
                b.to(device)
                if not isinstance(b, int) and not isinstance(b, list)
                else b
                for b in batch
            ]
            (
                input_ids,
                input_masks,
                segment_ids,
                slot_position_ids,
                gating_ids,
                domain_ids,
                target_ids,
                max_update,
                max_value,
                guids,
            ) = batch

            # teacher forcing
            if (
                    args.teacher_forcing_ratio > 0.0
                    and random.random() < args.teacher_forcing_ratio
            ):
                tf = target_ids
            else:
                tf = None

            with amp.autocast():

                domain_scores, state_scores, gen_scores = model(
                    input_ids=input_ids,
                    token_type_ids=segment_ids,
                    slot_positions=slot_position_ids,
                    attention_mask=input_masks,
                    max_value=max_value,
                    op_ids=gating_ids,
                    max_update=max_update,
                    teacher=tf,
                )

                # generation loss
                loss_1 = loss_fnc_1(
                    gen_scores.contiguous(),
                    target_ids.contiguous(),
                    tokenizer.pad_token_id,
                )

                # gating loss
                loss_2 = loss_fnc_2(
                    state_scores.contiguous().view(-1, 4),
                    gating_ids.contiguous().view(-1),
                )
                loss_3 = loss_fnc_2(domain_scores.view(-1, 5), domain_ids.view(-1))
                loss = loss_1 + loss_2 + loss_3

                loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
            # enc_optimizer.step()
            # enc_scheduler.step()
            # dec_optimizer.step()
            # dec_scheduler.step()
            # model.zero_grad()
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

            if step % 100 == 0:
                print(
                    f"[{epoch + args.ckpt}/{n_epochs + args.ckpt}] [{step}/{len(train_loader)}] loss: {loss.item()} gen: {loss_1.item()} gate: {loss_2.item()}, domain: {loss_3.item()}"
                )
                # if save:
                #     wandb.log(
                #         {
                #             "loss": loss.item(),
                #             "gen loss": loss_1.item(),
                #             "gate loss": loss_2.item(),
                #             "domain loss": loss_3.item(),
                #         }
                #     )

        predictions = inference(model, dev_examples, processor, device)
        eval_result = _evaluation(predictions, dev_labels, slot_meta)
        for k, v in eval_result.items():
            print(f"{k}: {v}")
        if save:
            wandb.log({
                "loss": loss.item(),
                "gen_loss": loss_1.item(),
                "gate_loss": loss_2.item(),
                "domain_loss": loss_3.item(),
                "joint_acc": eval_result['joint_goal_accuracy'],
                "turn_slot_acc": eval_result['turn_slot_accuracy'],
                "turn_slot_f1": eval_result['turn_slot_f1'],
            })
        if best_score < eval_result["joint_goal_accuracy"]:
            idx =(idx + 1) % 3
            print("Update Best checkpoint!")
            best_score = eval_result["joint_goal_accuracy"]
            best_checkpoint = epoch + args.ckpt
            if save:
                torch.save(model.state_dict(), f"{save_dir}/best_model{idx}.bin")
                save_info = {"model_name": f"best_model{idx}.bin", "epoch": epoch+args.ckpt, "JGA": best_score}
                json.dump(save_info, open(f"{save_dir}/best_model{idx}.json", "w"), indent=2, ensure_ascii=False)
        if epoch == 30 or epoch == 40:
            torch.save(model.state_dict(), f"{save_dir}/best_model{epoch}.bin")
            save_info = {"model_name": f"best_model{epoch}.bin", "epoch": epoch + args.ckpt, "JGA": eval_result["joint_goal_accuracy"]}
            json.dump(save_info, open(f"{save_dir}/best_model{epoch}.json", "w"), indent=2, ensure_ascii=False)
    torch.save(model.state_dict(), f"{save_dir}/last_model.bin")
    print(f"Best checkpoint: {save_dir}/model-{best_checkpoint}.bin")
