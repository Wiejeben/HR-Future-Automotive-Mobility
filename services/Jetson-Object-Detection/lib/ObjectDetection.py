import copy
from builtins import staticmethod, ord, sorted, set, list

import cv2
import numpy as np
import time

# Tensorflow
import tensorflow as tf
from tensorflow.core.framework import graph_pb2
# noinspection PyUnresolvedReferences
from object_detection.utils import label_map_util
# noinspection PyUnresolvedReferences
from object_detection.utils import visualization_utils as vis_util

# Internal
from lib.FPS import FPS
from lib.ThreadedSocketClient import ThreadedSocketClient
from lib.WebcamVideoStream import WebcamVideoStream
from lib.SessionWorker import SessionWorker


class ObjectDetection:
    # helper function for split model
    def __init__(self, config):
        self.video_stream = None
        self.socket_client = None
        self.fps = None
        self.cpu_worker = None
        self.gpu_worker = None
        self.cur_frames = 0
        self.config = config

    def start(self):
        graph = self.load_frozenmodel()
        category = self.load_labelmap()
        self.detection(graph, category)

    def load_frozenmodel(self):
        """Load a (frozen) Tensorflow model into memory."""
        print('> Loading frozen model into memory')
        if not self.config['split_model']:
            detection_graph = tf.Graph()
            with detection_graph.as_default():
                od_graph_def = tf.GraphDef()
                with tf.gfile.GFile(self.config['model_path'], 'rb') as fid:
                    serialized_graph = fid.read()
                    od_graph_def.ParseFromString(serialized_graph)
                    tf.import_graph_def(od_graph_def, name='')
            return detection_graph

        else:
            # load a frozen Model and split it into GPU and CPU graphs
            # Hardcoded for ssd_mobilenet
            input_graph = tf.Graph()
            with tf.Session(graph=input_graph):
                if self.config['ssd_shape'] == 600:
                    shape = 7326
                else:
                    shape = 1917
                tf.placeholder(tf.float32, shape=(None, shape, self.config['num_classes']),
                               name="Postprocessor/convert_scores")
                tf.placeholder(tf.float32, shape=(None, shape, 1, 4), name="Postprocessor/ExpandDims_1")
                for node in input_graph.as_graph_def().node:
                    if node.name == "Postprocessor/convert_scores":
                        score_def = node
                    if node.name == "Postprocessor/ExpandDims_1":
                        expand_def = node

            detection_graph = tf.Graph()
            with detection_graph.as_default():
                od_graph_def = tf.GraphDef()
                with tf.gfile.GFile(self.config['model_path'], 'rb') as fid:
                    serialized_graph = fid.read()
                    od_graph_def.ParseFromString(serialized_graph)
                    dest_nodes = ['Postprocessor/convert_scores', 'Postprocessor/ExpandDims_1']

                    edges = {}
                    name_to_node_map = {}
                    node_seq = {}
                    seq = 0
                    for node in od_graph_def.node:
                        n = self._node_name(node.name)
                        name_to_node_map[n] = node
                        edges[n] = [self._node_name(x) for x in node.input]
                        node_seq[n] = seq
                        seq += 1
                    for d in dest_nodes:
                        assert d in name_to_node_map, "%s is not in graph" % d

                    nodes_to_keep = set()
                    next_to_visit = dest_nodes[:]

                    while next_to_visit:
                        n = next_to_visit[0]
                        del next_to_visit[0]
                        if n in nodes_to_keep: continue
                        nodes_to_keep.add(n)
                        next_to_visit += edges[n]

                    nodes_to_keep_list = sorted(list(nodes_to_keep), key=lambda n: node_seq[n])
                    nodes_to_remove = set()

                    for n in node_seq:
                        if n in nodes_to_keep_list: continue
                        nodes_to_remove.add(n)
                    nodes_to_remove_list = sorted(list(nodes_to_remove), key=lambda n: node_seq[n])

                    keep = graph_pb2.GraphDef()
                    for n in nodes_to_keep_list:
                        keep.node.extend([copy.deepcopy(name_to_node_map[n])])

                    remove = graph_pb2.GraphDef()
                    remove.node.extend([score_def])
                    remove.node.extend([expand_def])
                    for n in nodes_to_remove_list:
                        remove.node.extend([copy.deepcopy(name_to_node_map[n])])

                    with tf.device('/gpu:0'):
                        tf.import_graph_def(keep, name='')
                    with tf.device('/cpu:0'):
                        tf.import_graph_def(remove, name='')

            return detection_graph

    def load_labelmap(self):
        print('> Loading label map')
        label_map = label_map_util.load_labelmap(self.config['label_path'])
        categories = label_map_util.convert_label_map_to_categories(
            label_map, max_num_classes=self.config['num_classes'], use_display_name=True
        )
        return label_map_util.create_category_index(categories)

    def exit(self):
        """End everything"""
        if self.config['split_model']:
            self.gpu_worker.stop()
            self.cpu_worker.stop()

        self.fps.stop()
        self.video_stream.stop()
        self.socket_client.stop()
        cv2.destroyAllWindows()
        print('> [INFO] elapsed time (total): {:.2f}'.format(self.fps.elapsed()))
        print('> [INFO] approx. FPS: {:.2f}'.format(self.fps.fps()))

    def detection(self, detection_graph, category_index):
        print("> Building Graph")
        # Session Config: allow seperate GPU/CPU adressing and limit memory allocation
        config = tf.ConfigProto(allow_soft_placement=True, log_device_placement=self.config['log_device'])
        config.gpu_options.allow_growth = self.config['allow_memory_growth']

        with detection_graph.as_default():
            with tf.Session(graph=detection_graph, config=config) as sess:
                # Define Input and Ouput tensors
                image_tensor = detection_graph.get_tensor_by_name('image_tensor:0')
                detection_boxes = detection_graph.get_tensor_by_name('detection_boxes:0')
                detection_scores = detection_graph.get_tensor_by_name('detection_scores:0')
                detection_classes = detection_graph.get_tensor_by_name('detection_classes:0')
                num_detections = detection_graph.get_tensor_by_name('num_detections:0')
                if self.config['split_model']:
                    score_out = detection_graph.get_tensor_by_name('Postprocessor/convert_scores:0')
                    expand_out = detection_graph.get_tensor_by_name('Postprocessor/ExpandDims_1:0')
                    score_in = detection_graph.get_tensor_by_name('Postprocessor/convert_scores_1:0')
                    expand_in = detection_graph.get_tensor_by_name('Postprocessor/ExpandDims_1_1:0')
                    # Threading
                    self.gpu_worker = SessionWorker('GPU', detection_graph, config)
                    self.cpu_worker = SessionWorker('CPU', detection_graph, config)
                    gpu_opts = [score_out, expand_out]
                    cpu_opts = [detection_boxes, detection_scores, detection_classes, num_detections]
                    gpu_counter = 0
                    cpu_counter = 0
                # Start Video Stream and FPS calculation
                self.fps = FPS(self.config['fps_interval']).start()
                self.video_stream = WebcamVideoStream(
                    self.config['video_input'],
                    self.config['width'],
                    self.config['height']).start()

                self.socket_client = ThreadedSocketClient(
                    category_index,
                    self.config['det_th'])
                self.socket_client.start()

                print('> Press \'q\' to Exit')
                print('> Starting Detection')
                while self.video_stream.is_active():
                    # actual Detection
                    if self.config['split_model']:
                        # split model in separate gpu and cpu session threads
                        if self.gpu_worker.is_sess_empty():
                            image = self.video_stream.read()
                            image_expanded = np.expand_dims(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), axis=0)
                            # put new queue
                            gpu_feeds = {image_tensor: image_expanded}
                            if self.config['visualize']:
                                gpu_extras = image  # for visualization frame
                            else:
                                gpu_extras = None
                            self.gpu_worker.put_sess_queue(gpu_opts, gpu_feeds, gpu_extras)

                        g = self.gpu_worker.get_result_queue()
                        if g is None:
                            # gpu thread has no output queue. ok skip, let's check cpu thread.
                            gpu_counter += 1
                        else:
                            # gpu thread has output queue.
                            gpu_counter = 0
                            score, expand, image = g['results'][0], g['results'][1], g['extras']

                            if self.cpu_worker.is_sess_empty():
                                # When cpu thread has no next queue, put new queue.
                                # else, drop gpu queue.
                                cpu_feeds = {score_in: score, expand_in: expand}
                                cpu_extras = image
                                self.cpu_worker.put_sess_queue(cpu_opts, cpu_feeds, cpu_extras)

                        c = self.cpu_worker.get_result_queue()
                        if c is None:
                            # cpu thread has no output queue. ok, nothing to do. continue
                            cpu_counter += 1
                            time.sleep(0.005)
                            continue  # If CPU RESULT has not been set yet, no fps update
                        else:
                            cpu_counter = 0
                            boxes, scores, classes, num, image = c["results"][0], c["results"][1], c["results"][2], \
                                                                 c["results"][3], c["extras"]
                    else:
                        # default session
                        image = self.video_stream.read()
                        image_expanded = np.expand_dims(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), axis=0)
                        boxes, scores, classes, num = sess.run(
                            [detection_boxes, detection_scores, detection_classes, num_detections],
                            feed_dict={image_tensor: image_expanded})

                    # Pass results to socket client
                    boxes = np.squeeze(boxes)
                    classes = np.squeeze(classes)
                    scores = np.squeeze(scores)

                    self.socket_client.boxes = boxes
                    self.socket_client.scores = scores
                    self.socket_client.classes = classes

                    # Visualization of the results of a detection.
                    if self.config['visualize']:
                        vis_util.visualize_boxes_and_labels_on_image_array(
                            image,
                            boxes,
                            classes.astype(np.int32),
                            scores,
                            category_index,
                            use_normalized_coordinates=True,
                            line_thickness=4)
                        if self.config['vis_text']:
                            cv2.putText(image, "fps: {}".format(self.fps.fps_local()), (10, 30),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (77, 255, 9), 2)
                        cv2.imshow('object_detection', image)
                        # Exit Option
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break

                    self.fps.update()

    @staticmethod
    def _node_name(n):
        if n.startswith("^"):
            return n[1:]
        else:
            return n.split(":")[0]
