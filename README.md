transfer learning from a source domain to a different target domain using adversarial training

To train the model, run the following command:
python main.py --train --model_name lstm/cnn --save_path model_name.pt 

To test the model, run the following command:
python main.py --test --model_name lstm/cnn --snapshot model_name.pt
