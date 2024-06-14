import argparse

import numpy as np
from peft import get_peft_model, TaskType, IA3Config
from transformers import BertTokenizer, BertForSequenceClassification, Trainer, TrainingArguments

from Logger import logger
from config import DataArgs, Config
from src.dataset import GlueDataset
from utils import count_trainable_parameters, save_results_to_json


def main(dataset_name: str):
    data_args = DataArgs()
    configuration = Config(
        task='ia3',
        dataset=dataset_name
    )
    # Define training arguments
    training_args = TrainingArguments(
        output_dir=configuration.MODEL_OUTPUT_DIR,
        num_train_epochs=configuration.EPOCHS,
        per_device_train_batch_size=configuration.BATCH_SIZE,
        per_device_eval_batch_size=configuration.BATCH_SIZE,
        warmup_steps=500,
        weight_decay=0.01,
        logging_dir='logs',
        logging_steps=10,

    )

    # Load the tokenizer, dataset and model
    tokenizer = BertTokenizer.from_pretrained(configuration.MODEL_NAME, do_lower_case=False)

    glue_dataset = GlueDataset(tokenizer, data_args=data_args, dataset_name=dataset_name, training_args=training_args)

    model = BertForSequenceClassification.from_pretrained(configuration.MODEL_NAME,
                                                          num_labels=glue_dataset.num_labels
                                                          )

    # set up lora config
    peft_config = IA3Config(
        task_type=TaskType.SEQ_CLS,
        inference_mode=False,
        # target_modules=[] -> if empty by default modules will be chosen according to the model architecture.
        # class IA3Config(PeftConfig)
        # (https://github.com/huggingface/peft/blob/v0.11.0/src/peft/tuners/ia3/config.py#L22
    )

    model = get_peft_model(model, peft_config)
    total_params, trainable_params = count_trainable_parameters(model)
    logger.info(
        f"Total parameters: {total_params} || Trainable parameters: {trainable_params} ({trainable_params / total_params * 100}%)")


    # Initialize the Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=glue_dataset.train_dataset,
        eval_dataset=glue_dataset.eval_dataset,
        tokenizer=tokenizer,
        data_collator=glue_dataset.data_collator,
        compute_metrics=glue_dataset.compute_metrics
    )

    # Train the model
    train_results = trainer.train()
    logger.info("Train results: %s", train_results.metrics)
    trainer.log_metrics("eval", train_results.metrics)
    trainer.save_metrics("eval", train_results.metrics)
    trainer.save_state()

    # set to evaluation mode
    model.eval()

    # evaluate the model
    eval_results = trainer.evaluate()
    logger.info("Evaluation results: %s", eval_results)
    trainer.log_metrics("eval", eval_results)
    trainer.save_metrics("eval", eval_results)

    # Save evaluation results to JSON
    save_results_to_json(
        configuration.RESULTS_PATH,
        'ia3',
        dataset_name,
        train_results=train_results,
        eval_results=eval_results,
        additional_comments={
            "trainable parameters": trainable_params,
            "total parameters": total_params,
            "trainable parameters ratio (%)": trainable_params / total_params * 100
        }
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run IA3")
    parser.add_argument('dataset', choices=['mnli', 'qnli', 'qqp', 'sst2'], help='Select the dataset to use')
    args = parser.parse_args()
    try:
        main(args.dataset)
    except Exception as ex:
        logger.error(f"Something went wrong {ex}")
