from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union, Any
import argparse
import pandas as pd
import ast
import numpy as np
import os
import json

from global_setting.state import GlobalState
from data.simulation.simulation import SimulationManager

# Update logic and priority of the state initialization
# 1. All values are intialized to None, later would be set its valid values by information exaction from the user query
# 2. The priority of the state initialization is from the user query > from the data > default values, if previously value is set, the later corresponding operation would be skipped

@dataclass
class UserData:
    raw_data: Optional[pd.DataFrame] = None
    processed_data: Optional[pd.DataFrame] = None
    ground_truth: Optional[np.ndarray] = None
    initial_query: Optional[str] = None
    knowledge_docs: Optional[str] = None

@dataclass
class Statistics:
    linearity: Optional[bool] = None
    gaussian_error: Optional[bool] = None
    missingness: Optional[bool] = None
    sample_size: Optional[int] = None
    feature_number: Optional[int] = None
    boot_num: int = 100
    alpha: float = 0.1
    num_test: int = 100
    ratio: float = 0.5
    data_type: Optional[str] = None
    heterogeneous: Optional[bool] = None
    domain_index: Optional[str] = None
    description: Optional[str] = None

@dataclass
class Logging:
    query_conversation: List[Dict] = field(default_factory=list)
    knowledge_conversation: List[Dict] = field(default_factory=list)
    filter_conversation: List[Dict] = field(default_factory=list)
    select_conversation: List[Dict] = field(default_factory=list)
    argument_conversation: List[Dict] = field(default_factory=list)
    errors_conversion: List[Dict] = field(default_factory=list)

@dataclass
class Algorithm:
    selected_algorithm: Optional[str] = None
    selected_reason: Optional[str] = None
    algorithm_candidates: Optional[Dict] = field(default_factory=dict)
    algorithm_arguments: Dict = field(default_factory=dict)
    waiting_minutes: float = 2.0

@dataclass
class Results:
    raw_result: Optional[object] = None
    raw_info: Optional[Dict] = None
    converted_graph: Optional[str] = None
    metrics: Optional[Dict] = None
    revised_graph: Optional[np.ndarray] = None
    revised_metrics: Optional[Dict] = None
    bootstrap_probability: Optional[np.ndarray] = None
    llm_errors: List[Dict] = field(default_factory=list)
    bootstrap_errors: List[Dict] = field(default_factory=list)

@dataclass
class GlobalState:
    user_data: UserData = field(default_factory=UserData)
    statistics: Statistics = field(default_factory=Statistics)
    logging: Logging = field(default_factory=Logging)
    algorithm: Algorithm = field(default_factory=Algorithm)
    results: Results = field(default_factory=Results)


def load_data(global_state: GlobalState, args: argparse.Namespace):
    if args.simulation_mode == "online":
        simulation_manager = SimulationManager(args)
        config, data, graph = simulation_manager.generate_dataset()
    elif args.simulation_mode == "offline":
        if args.data_mode == "simulated":
            config, data, graph = load_local_data(args.data_file)
        elif args.data_mode == "real":
            data = pd.read_csv(args.data_file)
            graph = None
        else:
            raise ValueError("Invalid data mode. Please choose 'real' or 'simulated'.")
    else:
        raise ValueError("Invalid simulation mode. Please choose 'online' or 'offline'.")
    
    global_state.user_data.raw_data = data
    global_state.user_data.ground_truth = graph

    # hard-coded heterogeneous and domain index, later would be set by the user query
    if 'domain_index' in data.columns:
        if data.nunique(axis=0)['domain_index'] > 1:
            global_state.statistics.heterogeneous = True
        else:
            global_state.statistics.heterogeneous = False
        global_state.statistics.domain_index = 'domain_index'

    return global_state

def load_local_data(directory: str):
    # Xinyue Wang Implemented
    '''
    :param directory: str for data directory
    :return: tuple of (config, data, graph)
    '''
    import json
    import os
    import pandas as pd
    import numpy as np

    if not os.path.exists(directory):
        raise FileNotFoundError(f"The directory {directory} does not exist.")

    config_path = f"{directory}/config.json"
    data_path = f"{directory}/base_data.csv"
    graph_path = f"{directory}/base_graph.npy"

    files = os.listdir(directory)

    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        config_path = None
        for file in files:
            if file.endswith(".json"):
                config_path = file
        if config_path != None:
            with open(os.path.join(directory, config_path), 'r') as f:
                config = json.load(f)
        else:
            config = None

    if os.path.exists(data_path):
        data = pd.read_csv(data_path)
    else:
        data_path = None
        for file in files:
            if file.endswith(".csv"):
                data_path = file
        if data_path != None:
            data = pd.read_csv(os.path.join(directory, data_path))
        else:
            raise FileNotFoundError(f"The data file {data_path} does not exist.")

    if os.path.exists(graph_path):
        graph = np.load(graph_path)
    else:
        graph_path = None
        for file in files:
            if file.endswith(".npy"):
                graph_path = file
        if graph_path != None:
            graph = np.load(os.path.join(directory, graph_path))
        else:
            graph = None

    return config, data, graph

def global_state_initialization(args: argparse.Namespace = None) -> GlobalState:
    user_query = args.initial_query
    global_state = GlobalState()

    global_state.user_data.initial_query = user_query

    # Extract information from user queries
    from openai import OpenAI
    import json

    client = OpenAI(organization=args.organization, project=args.project, api_key=args.apikey)
    prompt = (f"Based on the query that I provided: {user_query} \n\n; "
              "extract the following information and summarize them in a json format, and output this json object."
              "Within the output, the key, the corresponding value options and their meanings are: \n\n "
              "1. Describe whether the relationship between the variables are assumed to be linear or not:"
              "Key: 'linearity'. \n\n"
              "Options of value (bool): True, False. \n\n"
              "2. Describe whether the when fitting models between two variables, the error terms are assumed to be Gaussian or not:"
              "Key: 'gaussian_error'. \n\n"
              "Options of value (bool): True, False. \n\n"
              "3. The significance level (denoted as alpha) for doing statistical testing in the following analysis:"
              "Key: 'alpha'. \n\n"
              "Options of value (float): A numeric value that is greater than 0 and less than 1. \n\n"
              "4. Describe whether the dataset is heterogeneous or not:"
              "Key: 'heterogeneous'. \n\n"
              "Options of value (bool): True, False. \n\n"
              "5. If the dataset is heterogeneous, what is the name of the column in the dataset that represents the domain index:"
              "Key: 'domain_index'. \n\n"
              "Options of value (str): The name of the column that represents the domain index. \n\n"
              "6. Which algorithm the user would like to use to do causal discovery:"
              "Key: 'selected_algorithm'. \n\n"
              "Options of value (str): 'PC','FCI', 'CDNOD', 'GES', 'NOTEARS', 'DirectLiNGAM', 'ICALiNGAM'. \n\n"
              "7. How many minutes the user can wait for the causal discovery algorithm:"
              "Key: 'waiting_minutes'. \n\n"
              "Options of value (float): A numeric value that is greater than 0. \n\n"
              "However, for each key, if the value extracted from queries does not match provided options, or if the queries do not provide enough information and you cannot summarize them,"
              "the value for such key should be set to None! \n\n"
              "Just give me the output in a json format, do not provide other information! \n\n")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )

    # The output from GPT is str
    info_extracted = response.choices[0].message.content
    info_extracted = json.loads(info_extracted)

    # Assign extracted information from user queries to global_stat
    global_state.statistics.linearity = info_extracted["linearity"]
    global_state.statistics.gaussian_error = info_extracted["gaussian_error"]
    global_state.statistics.heterogeneous = info_extracted["heterogeneous"]
    global_state.statistics.domain_index = info_extracted["domain_index"]
    global_state.algorithm.selected_algorithm = info_extracted["selected_algorithm"]

    if info_extracted["waiting_minutes"] is not None:
        global_state.algorithm.waiting_minutes = info_extracted["waiting_minutes"]
    if info_extracted["alpha"] is not None:
        global_state.statistics.alpha = info_extracted["alpha"]

    return global_state




