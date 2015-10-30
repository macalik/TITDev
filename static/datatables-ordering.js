$(document).ready(function() {
    $('#cart_table').DataTable({
        "paging": false,
        "sDom": "lrtip"
    });
    $('table.datatables').DataTable({
        "lengthMenu": [[20, 50, 75, 100, -1], [20, 50, 75, 100, "All"]]
    });
} );