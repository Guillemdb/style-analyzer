"""Postprocess predictions of the model."""
import logging
from typing import Iterable, Mapping, Sequence

import bblfsh
from bblfsh.client import BblfshClient
from lookout.core.api.service_data_pb2 import File
import numpy

from lookout.style.format.feature_extractor import FeatureExtractor
from lookout.style.format.feature_utils import CLS_DOUBLE_QUOTE, CLS_SINGLE_QUOTE, \
    INDEX_CLS_TO_STR, VirtualNode


def check_uasts_are_equal(uast1: bblfsh.Node, uast2: bblfsh.Node) -> bool:
    """
    Check if 2 UASTs are identical or not in terms of nodes `roles`, `internal_type` and `token`.

    :param uast1: The bblfsh.Node of the first UAST to compare.
    :param uast2: The bblfsh.Node of the second UAST to compare.
    :return: A boolean equals to True if the 2 input UASTs are identical and False otherwise.
    """
    queue1 = [uast1]
    queue2 = [uast2]
    while queue1 or queue2:
        try:
            node1 = queue1.pop()
            node2 = queue2.pop()
        except IndexError:
            return False
        for child1, child2 in zip(node1.children, node2.children):
            if (child1.roles != child2.roles or child1.internal_type != child2.internal_type
                    or child1.token != child2.token):
                return False
        queue1.extend(node1.children)
        queue2.extend(node2.children)
    return True


def filter_uast_breaking_preds(y: numpy.ndarray, y_pred: numpy.ndarray,
                               vnodes_y: Sequence[VirtualNode], files: Mapping[str, File],
                               feature_extractor: FeatureExtractor, client: BblfshClient,
                               vnode_parents: Mapping[int, bblfsh.Node],
                               node_parents: Mapping[str, bblfsh.Node], log: logging.Logger
                               ) -> Iterable[int]:
    """
    Filter the model's predictions that modify the UAST apart from changing positions.

    :param y: Numpy 1-dimensional array of labels.
    :param y_pred: Numpy 1-dimensional array of predicted labels by the model.
    :param vnodes_y: Sequence of the labeled `VirtualNode`-s corresponding to labeled samples.
    :param files: Dictionary of File-s with content, uast and path.
    :param feature_extractor: FeatureExtractor used to extract features.
    :param client: Babelfish client.
    :param vnode_parents: `VirtualNode`-s' parents mapping as the LCA of the closest
                           left and right babelfish nodes.
    :param node_parents: Parents mapping of the input UASTs.
    :param log: Logger.
    :return: List of predictions indices that are considered valid i.e. that are not breaking
             the UAST.
    """
    CLS_QUOTES = {CLS_SINGLE_QUOTE, CLS_DOUBLE_QUOTE}
    safe_preds = []
    for i, (gt, pred, vn_y) in enumerate(zip(y, y_pred, vnodes_y)):
        if gt == pred:
            safe_preds.append(i)
            continue
        pred_string = "".join(INDEX_CLS_TO_STR[j] for j in
                              feature_extractor.labels_to_class_sequences[pred])
        if CLS_QUOTES.intersection(vn_y.value) and CLS_QUOTES.intersection(pred_string):
            safe_preds.append(i)
            continue
        content_before = files[vn_y.path].content
        parent = vnode_parents[id(vn_y)]
        errors_parsing = True
        while errors_parsing:
            start, end = parent.start_position.offset, parent.end_position.offset
            parse_response_before = client.parse(filename="", contents=content_before[start:end],
                                                 language=feature_extractor.language)
            if parse_response_before.errors:
                parent = node_parents[id(parent)]
                continue
            errors_parsing = parse_response_before.errors
            diff_pred_offset = len(pred_string) - len(vn_y.value)
            content_after = content_before[:vn_y.start.offset] \
                + pred_string.encode() \
                + content_before[vn_y.start.offset - diff_pred_offset + 1:]
            content_after = content_after[start:end + diff_pred_offset]
            parse_response_after = client.parse(filename="", contents=content_after,
                                                language=feature_extractor.language)
            if not parse_response_after.errors:
                parent_after = parse_response_after.uast
                parent_before = parse_response_before.uast
                if check_uasts_are_equal(parent_before, parent_after):
                    safe_preds.append(i)
    log.info("Non UAST breaking predictions: %d selected out of %d",
             len(safe_preds), y_pred.shape[0])
    vnodes_y = [vn for i, vn in enumerate(list(vnodes_y)) if i in safe_preds]
    return y[safe_preds], y_pred[safe_preds], vnodes_y, safe_preds
