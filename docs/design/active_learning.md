# Active learning

`active_learning_priority = 0.30*uncertainty + 0.20*evaluator_disagreement +
0.20*business_risk + 0.10*novelty + 0.10*cost_surprise +
0.10*policy_value_of_information`. Items at/above threshold (default 0.25) or
flagged as audit samples are selected for human labeling, feeding the reward and
supervised/bandit learners.
