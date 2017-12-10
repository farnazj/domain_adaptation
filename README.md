#domain adaptation
To train the model, run the following command:
python main.py --train --model_name lstm/cnn --save_path model_name.pt 

To test the model, run the following command:
python main.py --test --model_name lstm/cnn --snapshot model_name.pt

Download embeddings from https://www.dropbox.com/s/f62hw5wivjbksxl/glove.emb.zip?dl=0
and put the file in root folder (along with main.py)
