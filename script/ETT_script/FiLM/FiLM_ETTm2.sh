export CUDA_VISIBLE_DEVICES=1

python -u run.py \
  --is_training 1 \
  --root_path ./dataset/ETT-small/ \
  --data_path dataset.csv \
  --model_id FiLM_ETTm2_96_96 \
  --model FiLM \
  --data dataset \
  --features S \
  --seq_len 96 \
  --label_len 48 \
  --pred_len 96 \
  --e_layers 2 \
  --d_layers 1 \
  --factor 1 \
  --enc_in 1 \
  --dec_in 1 \
  --c_out 1 \
  --des 'Exp' \
  --itr 1 \
  --lradj type4 \
  --learning_rate 1e-3 \
  --patience 30 \
  --train_epochs 1 \
  --modes1 32 \
  --ab 2 --ours 

#python -u run.py \
 # --is_training 1 \
 # --root_path ./dataset/ETT-small/ \
  #--data_path ETTm2.csv \
  #--model_id FiLM_ETTm2_96_192 \
  #--model FiLM  \
  #--data ETTm2 \
  #--features M \
  #--seq_len 720 \
  #--label_len 48 \
  #--pred_len 192 \
  #--e_layers 2 \
  #--d_layers 1 \
 # --factor 1 \
  #--enc_in 7 \
  #--dec_in 7 \
  #--c_out 7 \
  #--des 'Exp' \
  #--itr 1 \
  #--lradj type4 \
  #--learning_rate 1e-3 \
  #--patience 30 \
  #--train_epochs 30 \
  #--modes1 32 \
  #--ab 2 --ours 

#python -u run.py \
 # --is_training 1 \
  #--root_path ./dataset/ETT-small/ \
  #--data_path ETTm2.csv \
  #--model_id FiLM_ETTm2_96_336 \
  #--model FiLM  \
  #--data ETTm2 \
  #--features M \
  #--seq_len 720 \
  #--label_len 48 \
  #--pred_len 336 \
  #--e_layers 2 \
  #--d_layers 1 \
  #--factor 1 \
  #--enc_in 7 \
  #--dec_in 7 \
  #--c_out 7 \
  #--des 'Exp' \
  #--itr 1 \
  #--lradj type4 \
  #--learning_rate 1e-3 \
  #--patience 30 \
  #--train_epochs 30 \
  #--modes1 32 \
  #--ab 2 --ours 

#python -u run.py \
 # --is_training 1 \
  #--root_path ./dataset/ETT-small/ \
  #--data_path ETTm2.csv \
  #--model_id FiLM_ETTm2_96_720 \
  #--model FiLM \
  #--data ETTm2 \
  #--features M \
  #--seq_len 2840 \
  #--label_len 48 \
  #--pred_len 720 \
  #--e_layers 2 \
 # --d_layers 1 \
 # --factor 1 \
  #--enc_in 7 \
  #--dec_in 7 \
  #--c_out 7 \
  #--des 'Exp' \
  #--itr 1 \
  #--lradj type4 \
  #--learning_rate 1e-3 \
  #--patience 30 \
  #--train_epochs 30 \
  #--batch_size 16 \
  #--modes1 32 \
  #--ab 2 --ours 
