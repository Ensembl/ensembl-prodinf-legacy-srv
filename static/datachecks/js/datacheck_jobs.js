function expandIcon(value, row , index){
  return '<span title="Click for more info" style="cursor: pointer; color:blue" class="fas fa-plus" onclick="row_details('+ index +')">+</span> <span class="fa fa-plus"></span>'
}

function row_details(id){
 let table = $('#table');
 console.log(table);
 table.bootstrapTable('expandRow', id);
}

function downloadFormat(value, row){

  let cursor_download = 'not-allowed';
  let download_event = 'pointer-events:none';
  if(row.status == 'complete' || row.status == 'failed'){
    cursor_download = 'pointer';
    download_event = ''; 
  }
  return '<a title="Dowload DC.. " style="cursor:'+ cursor_download +'; '+ download_event +'"  href="/datacheck/download_datacheck_outputs/'+ row.id  +' ">'+ row.id +'</a>'
}


function detailPage(value, row){
  return '<a title="More details " style="cursor: pointer"  href="/datacheck/jobs/'+ row.id  +' ">'+ row.id +'</a>'
}

function statusFormat(value, row){
     let class_name = 'badge-success';
     let html = [];
     if (value == 'incomplete'){
         class_name = 'badge-primary';
         return '<span class="badge ' + class_name +'">'+ value +'</span><br>'
     }   
     if(value == 'failed'){
      return '<span class="badge badge-danger">'+ value +'</span>'
    }
     return '<span class="badge ' + class_name +'">'+ value +'</span>'
}

function FormatArrayName(value, row){
  let html = ''; 
  if( value ){
    for(let i=0; i<value.length; i++){
        html = html + value[i] + ' ';
    }
    return html;
  }else{
    return 'NA';
  }

}

function FormatTimestamp(value){

  if(value){
   return value.timestamp;
  }
  else{ return '-';}
}




function parseJobs(row, type){
      let html = [];
      html.push('<div class="m-2" id="accordionIO">');    
      //heading 
     html.push('<div class="card-header" id="' + row.id + type + '">' +  
                '<h2 class="mb-0">'                     +
                '<button class="btn btn-outline-info btn-link" type="button" data-toggle="collapse" data-target="#collapseOne'+ row.id + type + '" aria-expanded="true" aria-controls="collapseOne">' +
                type +
                '</button>' +
                '</h2>' +
                '</div>');        



      html.push('<div id="collapseOne' + row.id + type +'" class="collapse " aria-labelledby="' + row.id + type + '" data-parent="#accordionIO">');
      html.push('<div class="card mb-2">')
      html.push('<div class="card-body">')
      html.push('<h5 class="card-title">'+type +' :</h5>')
      html.push('<hr>');
      html.push('<table class="table table-striped">')
     $.each(row[type], function (key, value) {
       if(key !== 'databases'){
         html.push('<tr>')
         html.push('<td><b>' + key + '</b></td><td>' + value + '</td>')
         html.push('</tr>');
       }
     });
     html.push('</table>')
     html.push('</div>')
     html.push('</div>')  
 
     html.push('</div>')  
 
    html.push('</div>') //IO  

     return html.join('')
}

function parseDatabases(row){
      let html = [];
      let database_count = 0;
      html.push('<div class="m-2" id="accordionDB">');   
      html.push('<div class="card-header" id="DB' + row.id  + '">' +
                '<h2 class="mb-0">'                     +
                '<button class="btn btn-outline-info btn-link" type="button" data-toggle="collapse" data-target="#collapseOneDB'+ row.id + '" aria-expanded="true" aria-controls="collapseOne"> Database:' +
                '</button>' +
                '</h2>' +
                '</div>');

      html.push('<div id="collapseOneDB' + row.id +'" class="collapse " aria-labelledby="DB' + row.id  + '" data-parent="#accordionDB">');    
      html.push('<div class="card ">')
      html.push('<div class="card-body">')
      html.push('<h5 class="card-title">DataBase  :</h5>')
      html.push('<div id="accordion">')
      html.push('<hr>')
      $.each(row.output.databases, function (key, value) {
         database_count++;
         let db_name = key;
         html.push('<div class="card m-2"> <div class="card-header" id="'+ key + 'headingOne"><h5 class="mb-2">')
         html.push('<button class="btn btn-link">')
         html.push(key + '</button><button class="btn btn-primary pull-right" style="right: 0"'
         + ' data-toggle="collapse" data-target="#' + key + '" aria-expanded="true" aria-controls="collapseOne"' 
         + ' Onclick="getdetails('+ row.id 
         +  ", '" + row.output.json_output_file 
         + "' , '" + db_name + "'"
         +')">Details</button></h5></div>')
         html.push('<div id="'+ key +'" class="collapse m-2" aria-labelledby="'+ key + 'headingOne" data-parent="#accordion">')
         html.push('<div class="card-body m-2">')
         //html.push('<h5 class="card-title">'+ key  +':</h5>')
         html.push('<table class="table table-striped m-2">')       
         $.each(row.output.databases[key], function (key, value) {
            html.push('<tr>')
            html.push('<td><b>' + key + '</b></td><td>' + value + '</td>')
            html.push('</tr>');
         });
         html.push('</table>')        
         html.push('</div>')
         html.push('<div id="'+db_name+'_details"></div>')
         html.push('</div>')
         html.push('</div>')
     
      });

      html.push('</div>')
      html.push('</div>')
      html.push('</div>')
 
      html.push('</div>') //colloaspe db

      html.push('</div>') //accordion DB
     if (database_count == 0){
       return ''; 
     }
     return html.join('') 
}

function detailFormatter(index, row) {
    var html = []
    if(row.status == 'incomplete'){ 
       html.push(parseJobs(row, 'input'));
    }else{

      html.push(parseJobs(row, 'input'));
      html.push(parseJobs(row, 'output'));
      html.push(parseDatabases(row));
    }
    return html.join('')
}


function getdetails(id, json_path, db_name){

    document.getElementById(db_name+'_details').innerHTML = '<div class="d-flex justify-content-center"> <div class="spinner-border" role="status"> <span class="sr-only">Loading...</span> </div> </div></div>';
    //send proper url  
    $.getJSON('/datacheck/jobs/details?jsonfile=' + json_path, function(result){
        console.log(result);
        let details = parse_details(db_name, result);
        document.getElementById(db_name+'_details').innerHTML = details;
    });
}


function parse_details(db_name, result){

   let html= [];
   let card_header = '';
   let datacheck_html = [];
   //html.push('<h4>Species:</h4><hr>');
   $.each(result, function (species, value) {
        species = species.split(" ").join("").split(",").join("");
        card_header = "border-primary ";
        datachecks_failed = 0 ;
	$.each(value, function (datachecks, value1) {
            let datacheck_bordear = "border-primary ";
            let test_html =[]; 
            if( value1["ok"] == 0 ){ datachecks_failed++; card_header = "border-danger "; datacheck_bordear = "border-danger ";} 
            test_html.push('<table class="tabletable-responsive table-striped m-2">');
            $.each(value1["tests"], function (each_test, value2) {
                let table_success = 'table-success';
                if(each_test.startsWith("not")){ table_success='table-danger';}
		test_html.push('<tr class="' + table_success +' m-2"><td class="m-2">' + each_test +  '</td></tr>');
            }); 
            test_html.push('</table>'); 
            datacheck_html.push('<div id="accordion_datacheck" class="m-2">');
            datacheck_html.push('<div class="card m-2'+ datacheck_bordear +' mb-3"> <div class="card-header" id="'+ species + '_' + datachecks + 'headingOne"><h5 class="mb-0">');
            datacheck_html.push('<button class="btn btn-link" data-toggle="collapse" data-target="#' + species + '_' + datachecks + '"  aria-expanded="true" aria-controls="'+ species + '_' + datachecks + '">');
            datacheck_html.push(datachecks + '</button></h5></div>');
            datacheck_html.push(test_html.join(''));  
            datacheck_html.push('</div>');
            datacheck_html.push('</div>');
	});
        let failed_badge = '';
        if(datachecks_failed > 0){ failed_badge= '<span class="badge badge-danger">Failed:'+ datachecks_failed +'</span>';}
        html.push('<div id="accordion_species" class="border-danger">');
        html.push('<div class="card m-2'+ card_header +' mb-3"> <div class="card-header" id="'+ species + 'headingOne"><h5 class="mb-0">');
        html.push('<button class="btn btn-link" data-toggle="collapse" data-target="#' + species + '"  aria-expanded="true" aria-controls="'+ species + '">');
        html.push(species + '</button>'+ failed_badge +'</h5></div>');
        html.push('<div id= "' + species + '"class="collapse"   aria-labelledby="'+ species + 'headingOne" data-parent="#accordion_species">');
        //html.push('<h4>Datachecks::</h4><hr>') 
        html.push(datacheck_html.join(''));
        html.push('</div>');	    
        html.push('</div>');
        datacheck_html =[];
   });

  console.log(card_header);

  return html.join('')
}








function rowStyle(row, index) {
    var $table = $('#table')
    let color='';
   /* if(row.status == 'complete'){
    }*/
    return {
      css:{
        // 'background-color': color
      }
    }
  }


$(document).ready(function(){

  var $table = $('#table')
  $table.bootstrapTable('refreshOptions', {
        theadClasses: 'bg-purple'
  });

  $table.bootstrapTable('expandAllRows');
  $(".search").removeClass("float-right");
  $(".search").addClass("float-left");
  //$(".search").prepend('<input type="number" min=0  id="myjob_id" class="form-control search-input" placeholder="job id"><button class="btn btn-primary job_btn mr-3">View</button>');
  // get the job details
  /*$(".job_btn").click(function(){
       let job_id = $("#myjob_id").val();
             //this will redirect us in same window
             document.location.href = "/datacheck/jobs/" + job_id
  });*/
});
