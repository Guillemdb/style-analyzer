"""
Command line utilities to check the quality of a model on a given dataset, visualize errors, etc.
"""
from argparse import ArgumentParser
import json
import os
from typing import Any, Mapping

from lookout.core.cmdline import ArgumentDefaultsHelpFormatterNoNone
from modelforge import slogging
import pandas

from lookout.style.typos.preparation import DEFAULT_CORRECTOR_CONFIG, get_datasets, prepare_data, \
    train_and_evaluate, train_fasttext, train_from_scratch


def add_config_arg(my_parser: ArgumentParser) -> None:
    """
    Add config argument.

    :param my_parser: Parser to add the argument to.
    """
    my_parser.add_argument(
        "--config", required=False, type=json.loads, default="{}",
        help="Config for in json format.")


def add_data_path_arg(my_parser: ArgumentParser) -> None:
    """
    Add data path argument.

    :param my_parser: Parser to add the argument to.
    """
    my_parser.add_argument(
        "--data-path", required=False, type=str,
        default=os.path.join(DEFAULT_CORRECTOR_CONFIG["preparation"]["data_dir"],
                             DEFAULT_CORRECTOR_CONFIG["preparation"]["prepared_filename"]),
        help=".csv dump of a Dataframe with columns Columns.Split and Columns.Frequency.")


def add_corrector_path_arg(my_parser: ArgumentParser) -> None:
    """
    Add save model path argument.

    :param my_parser: Parser to add the argument to.
    """
    my_parser.add_argument(
        "--corrector-path", required=False, type=str,
        default=DEFAULT_CORRECTOR_CONFIG["corrector_path"],
        help="Path to save the trained model to (.asdf).")


def cli_train_fasttext(data_path: str, config: Mapping[str, Any]) -> None:
    """Entry point for `train_fasttext`."""
    train_fasttext(pandas.read_csv(data_path, index_col=0, keep_default_na=False), config)


def cli_get_datasets(data_path: str, config: Mapping[str, Any]) -> None:
    """Entry point for `get_datasets`."""
    get_datasets(pandas.read_csv(data_path, index_col=0, keep_default_na=False), config)


def cli_train_corrector(train: str, test: str, vocabulary_path: str,
                        frequencies_path: str, fasttext_path: str, corrector_path: str,
                        config: Mapping[str, Any]) -> None:
    """Entry point for `train_and_evaluate`."""
    train = pandas.read_csv(train, index_col=0, keep_default_na=False)
    test = pandas.read_csv(test, index_col=0, keep_default_na=False)
    model = train_and_evaluate(train, test, vocabulary_path, frequencies_path, fasttext_path,
                               config.get("generation", {}), config.get("ranking", {}))
    model.save(corrector_path, series=0.0)


def create_parser() -> ArgumentParser:
    """
    Create a parser for the lookout.style.typos utility.

    :return: an ArgumentParser with an handler defined in the handler attribute.
    """
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatterNoNone)

    # General options
    slogging.add_logging_args(parser)
    subparsers = parser.add_subparsers(help="Commands")

    def add_parser(name, help):
        return subparsers.add_parser(
            name, help=help, formatter_class=ArgumentDefaultsHelpFormatterNoNone)

    # Prepare raw data for corrector
    prepare_parser = add_parser("prepare-data", "Prepare raw dataset for corrector training.")
    prepare_parser.set_defaults(handler=prepare_data)
    add_config_arg(prepare_parser)

    # Train new fasttext model on gien data
    fasttext_parser = add_parser("train-fasttext", "Train fasttext model on the given dataset"
                                                   "of code identifiers.")
    fasttext_parser.set_defaults(handler=cli_train_fasttext)
    add_data_path_arg(fasttext_parser)
    add_config_arg(fasttext_parser)

    # Create train and test datasets with artificial typos
    datasets_parser = add_parser("get-datasets",
                                 "Create the train and the test datasets of typos.")
    datasets_parser.set_defaults(handler=cli_get_datasets)
    add_data_path_arg(datasets_parser)
    add_config_arg(datasets_parser)

    # Create, train and evaluate new corrector model
    train_parser = add_parser("train", "Create and train TyposCorrector model on the given data.")
    train_parser.set_defaults(handler=cli_train_corrector)
    train_parser.add_argument(
        "--train", required=False, type=str,
        default=DEFAULT_CORRECTOR_CONFIG["datasets"]["train_path"],
        help=".csv dump of a Dataframe with columns Columns.Split and Columns.Frequency.",
    )
    train_parser.add_argument(
        "--test", required=False, type=str,
        default=DEFAULT_CORRECTOR_CONFIG["datasets"]["test_path"],
        help=".csv dump of a Dataframe with columns Columns.Split and Columns.Frequency.",
    )
    train_parser.add_argument(
        "-v", "--vocabulary-path", required=False, type=str,
        default=os.path.join(DEFAULT_CORRECTOR_CONFIG["preparation"]["data_dir"],
                             DEFAULT_CORRECTOR_CONFIG["preparation"]["vocabulary_filename"]),
        help="Path to a .csv file with vocabulary.",
    )
    train_parser.add_argument(
        "-f", "--frequencies-path", required=False, type=str,
        default=os.path.join(DEFAULT_CORRECTOR_CONFIG["preparation"]["data_dir"],
                             DEFAULT_CORRECTOR_CONFIG["preparation"]["frequencies_filename"]),
        help="Path to a .csv file with tokens' frequencies.",
    )
    train_parser.add_argument(
        "-e", "--fasttext-path", required=False, type=str,
        default=DEFAULT_CORRECTOR_CONFIG["fasttext"]["path"],
        help="Path to a FastText model's dump (.bin).",
    )
    add_config_arg(train_parser)
    add_corrector_path_arg(train_parser)

    ########################################
    # One command to rule them all
    ########################################
    train_from_scratch_parser = add_parser(
        "train-from-scratch", "Create and train TyposCorrector model on the given data.")
    train_from_scratch_parser.set_defaults(handler=train_from_scratch)
    add_config_arg(train_from_scratch_parser)

    return parser


def main() -> Any:
    """Entry point of the utility."""
    parser = create_parser()
    args = parser.parse_args()
    for log_arg in ("log_level", "log_structured", "log_config"):
        delattr(args, log_arg)
    try:
        handler = args.handler
        delattr(args, "handler")
    except AttributeError:
        def print_usage(*args, **kwargs):
            parser.print_usage()

        handler = print_usage
    return handler(**vars(args))
