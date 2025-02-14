import argparse
import json
import os
import random
import wandb
import pickle
import time

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, RandomSampler, SequentialSampler
from tqdm import tqdm
from transformers import AdamW, BertTokenizer, get_linear_schedule_with_warmup

from data_utils import (WOSDataset, get_examples_from_dialogues, load_dataset,
                        set_seed)
from eval_utils import DSTEvaluator, eval_wrong_count
from evaluation import _evaluation
from inference import inference_trade, inference_sumbt
from model import TRADE, masked_cross_entropy_for_value, SUMBT
from preprocessor import TRADEPreprocessor, SUMBTPreprocessor
from torch.cuda.amp import autocast, GradScaler
from pprint import pprint

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
use_amp = False


def train(args):
    # random seed 고정
    set_seed(args.random_seed)

    # Data Loading
    train_data_file = f"{args.data_dir}/train_dials.json"
    train_data, dev_data, dev_labels = load_dataset(train_data_file)
    slot_meta = json.load(open(f"{args.data_dir}/slot_meta.json"))  # 45개의 slot

    # Define Preprocessor
    tokenizer = BertTokenizer.from_pretrained(args.model_name_or_path)
    processor = TRADEPreprocessor(slot_meta, tokenizer)
    args.vocab_size = len(tokenizer)
    args.n_gate = len(processor.gating2id)  # gating 갯수 none, dontcare, ptr

    with open('trade_data/train_features.bin', 'rb') as f:
        train_features = pickle.load(f)
    with open('trade_data/dev_features.bin', 'rb') as f:
        dev_features = pickle.load(f)

    # Slot Meta tokenizing for the decoder initial inputs
    tokenized_slot_meta = []
    slot_wrong_count = {}
    for slot in slot_meta:
        slot_wrong_count[slot] = 0
        tokenized_slot_meta.append(
            tokenizer.encode(slot.replace("-", " "), add_special_tokens=False)
        )

    # Model 선언
    model = TRADE(args, tokenized_slot_meta, slot_meta)

    model.to(device)
    if args.wandb_name:
        wandb.init(project='pstage3', entity='ekzm8523')
        wandb.config.update(args)
        wandb.run.name = args.wandb_name
        wandb.watch(model)
    print("Model is initialized")

    train_data = WOSDataset(train_features)  # feature와 len만 담긴 dataset
    train_sampler = RandomSampler(train_data)  #
    train_loader = DataLoader(
        train_data,
        batch_size=args.train_batch_size,
        sampler=train_sampler,
        collate_fn=processor.collate_fn,
    )

    print("# train:", len(train_data))

    dev_data = WOSDataset(dev_features)
    dev_sampler = SequentialSampler(dev_data)
    dev_loader = DataLoader(
        dev_data,
        batch_size=args.eval_batch_size,
        sampler=dev_sampler,
        collate_fn=processor.collate_fn,

    )
    print("# dev:", len(dev_data))

    # Optimizer 및 Scheduler 선언
    n_epochs = args.epochs
    t_total = len(train_loader) * n_epochs
    warmup_steps = int(t_total * args.warmup_ratio)
    optimizer = AdamW(model.parameters(), lr=args.learning_rate, eps=args.adam_epsilon)
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=t_total
    )

    loss_fnc_1 = masked_cross_entropy_for_value  # generation
    loss_fnc_2 = nn.CrossEntropyLoss()  # gating


    if not os.path.exists(args.model_dir):
        os.mkdir(args.model_dir)
    if not os.path.exists(f"{args.model_dir}/{args.model}"):
        os.mkdir(f"{args.model_dir}/{args.model}")

    json.dump(
        vars(args),
        open(f"{args.model_dir}/{args.model}/exp_config.json", "w"),
        indent=2,
        ensure_ascii=False,
    )

    json.dump(
        slot_meta,
        open(f"{args.model_dir}/{args.model}/slot_meta.json", "w"),
        indent=2,
        ensure_ascii=False,
    )
    best_score, best_checkpoint = 0, 0
    for epoch in range(n_epochs):
        start = time.time()
        model.train()
        for step, batch in enumerate(train_loader):
            input_ids, segment_ids, input_masks, gating_ids, target_ids, guids = [
                # gating_ids는 target_ids의 어디를 봐야하는지 알려
                b.to(device) if not isinstance(b, list) else b for b in batch
            ]

            # teacher forcing
            if args.teacher_forcing_ratio > 0.0 and random.random() < args.teacher_forcing_ratio:
                tf = target_ids
            else:
                tf = None
            all_point_outputs, all_gate_outputs = model(input_ids, segment_ids, input_masks, target_ids.size(-1))

            # generation loss
            loss_1 = loss_fnc_1(
                all_point_outputs.contiguous(),
                target_ids.contiguous().view(-1),  # flatten
                tokenizer.pad_token_id,
            )

            # gating loss
            loss_2 = loss_fnc_2(
                all_gate_outputs.contiguous().view(-1, args.n_gate),
                gating_ids.contiguous().view(-1),
            )
            loss = loss_1 + loss_2

            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

            if step % 100 == 0:
                print(
                    f"[{epoch}/{n_epochs}] [{step}/{len(train_loader)}] loss: {loss.item()} gen: {loss_1.item()} gate: {loss_2.item()} time: {int(time.time() - start)}second"
                )

        predictions = inference_trade(model, dev_loader, processor, device)
        wrong_value, wrong_slot = eval_wrong_count(predictions, dev_labels)
        eval_result = _evaluation(predictions, dev_labels, slot_meta)
        for k, v in eval_result.items():
            print(f"{k}: {v}")

        print("---------------wrong value top 10-----------------")
        print(f" 걸린 시간 : {int(time.time() - start)} 초")
        pprint(wrong_value)
        print("---------------wrong slot top 10------------------")
        pprint(wrong_slot)
        print("-" * 50)
        if args.wandb_name:
            wandb.log({
                "loss": loss.item(),
                "gen_loss": loss_1.item(),
                "gate_loss": loss_2.item(),
                "joint_acc": eval_result['joint_goal_accuracy'],
                "turn_slot_acc": eval_result['turn_slot_accuracy'],
                "turn_slot_f1": eval_result['turn_slot_f1'],
            })
        if best_score < eval_result['joint_goal_accuracy']:
            print("Update Best checkpoint!")
            best_score = eval_result['joint_goal_accuracy']
            best_checkpoint = epoch
            torch.save(model.state_dict(), f"{args.model_dir}/{args.model}/best_model.bin")
    print(f"Best checkpoint: {args.model_dir}/model-{best_checkpoint}.bin")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default="/opt/ml/input/data/train_dataset")
    parser.add_argument("--model_dir", type=str, default="/opt/ml/model/")
    parser.add_argument("--model", type=str, default="trade", help="select trade or sumbt")
    parser.add_argument("--train_batch_size", type=int, default=16)
    parser.add_argument("--eval_batch_size", type=int, default=8)
    parser.add_argument("--learning_rate", type=float, default=3e-5)
    parser.add_argument("--adam_epsilon", type=float, default=1e-8)
    parser.add_argument("--max_grad_norm", type=float, default=1.0)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--warmup_ratio", type=int, default=0.1)
    parser.add_argument("--random_seed", type=int, default=42)
    parser.add_argument(
        "--model_name_or_path",
        type=str,
        help="Subword Vocab만을 위한 huggingface model",
        default="dsksd/bert-ko-small-minimal",
    )

    # Model Specific Argument
    parser.add_argument("--hidden_size", type=int, help="GRU의 hidden size", default=768)
    parser.add_argument(
        "--vocab_size",
        type=int,
        help="vocab size, subword vocab tokenizer에 의해 특정된다",
        default=None,
    )

    parser.add_argument("--hidden_dropout_prob", type=float, default=0.1)
    parser.add_argument("--proj_dim", type=int,
                        help="만약 지정되면 기존의 hidden_size는 embedding dimension으로 취급되고, proj_dim이 GRU의 hidden_size로 사용됨. hidden_size보다 작아야 함.",
                        default=None)
    parser.add_argument("--teacher_forcing_ratio", type=float, default=0.5)
    parser.add_argument("--wandb_name", type=str, default=None)
    args = parser.parse_args()
    print(args)
    train(args)
