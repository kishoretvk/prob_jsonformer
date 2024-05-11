from jaxtyping import Float, Int
import torch
from torch.nn import functional as F
from torch import Tensor
from typing import List, Callable, Tuple, Dict, Optional
import pandas as pd
from transformers import AutoModelForCausalLM, AutoTokenizer


def get_valid_next_choices(choices_tokens, current_tokens):
    next_choices = []
    for choice_tokens in choices_tokens:
        # if we have some more slots left
        if len(current_tokens) < len(choice_tokens):
            # see if current_tokens matches
            if (choice_tokens[: len(current_tokens)] == current_tokens).all():
                c = choice_tokens[len(current_tokens)].item()
                next_choices.append(c)

    next_choices = list(set(next_choices))
    return torch.LongTensor(next_choices)


def _choice_tree(
    model: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    input_ids: Int[Tensor, "seq"],
    choices_tokens: List[Int[Tensor, "seq"]],
    choice: Optional[Int[Tensor, ""]] = None,
    prob: float = 1,
    current_tokens: Int[Tensor, "seq"] = torch.LongTensor([]),
):
    if choice is not None:
        c = choice[None].to(current_tokens.device)
        current_tokens = torch.cat([current_tokens, c], dim=-1)
        c = choice[None].to(input_ids.device)
        input_ids = torch.cat([input_ids, c], dim=-1)

    next_choices = get_valid_next_choices(choices_tokens, current_tokens)
    if len(next_choices) == 0:
        s = tokenizer.decode(current_tokens, skip_special_tokens=True)
        r = dict(prob=prob, choice=s)
        yield r
    else:
        o = model(input_ids[None])
        logits_constrained = o.logits[0, -1][next_choices]
        probs = F.softmax(logits_constrained, dim=-1)
        for i in range(len(next_choices)):
            next_choice = next_choices[i]
            next_prob = prob * probs[i].item()
            yield from choice_tree(
                model=model,
                tokenizer=tokenizer,
                choices_tokens=choices_tokens,
                input_ids=input_ids,
                choice=next_choice,
                prob=next_prob,
                current_tokens=current_tokens,
            )


def choice_tree(
    *args,
    **kwargs,
):
    choice_json = list(
        _choice_tree(
            *args,
            **kwargs,
        )
    )
    # order by probability
    choice_json = sorted(choice_json, key=lambda x: -x["prob"])
    return choice_json
